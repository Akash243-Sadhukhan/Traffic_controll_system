


import argparse
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pandas as pd
from tqdm import tqdm

import torch
from torch.utils.data import Dataset, DataLoader
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
import torchvision.transforms as T


class CSVObjectDetectionDataset(Dataset):
    """Custom dataset reading a CSV with bounding boxes.
    Expects columns: filename,xmin,ymin,xmax,ymax,label
    Multiple rows may refer to the same image.
    """

    def __init__(self, images_dir, annotations_csv, transforms=None):
        self.images_dir = images_dir
        self.annotations = pd.read_csv(annotations_csv)
        # Group annotations by filename for faster indexing
        grouped = self.annotations.groupby('filename')
        self.image_files = list(grouped.groups.keys())
        self.annotations_groups = {fname: grouped.get_group(fname) for fname in self.image_files}
        self.transforms = transforms

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, idx):
        fname = self.image_files[idx]
        img_path = os.path.join(self.images_dir, fname)
        img = Image.open(img_path).convert("RGB")
        ann = self.annotations_groups[fname]

        boxes = ann[['xmin', 'ymin', 'xmax', 'ymax']].values.astype(np.float32)
        labels = ann['label'].values.astype(np.int64)

        # convert to tensors
        boxes = torch.as_tensor(boxes, dtype=torch.float32)
        labels = torch.as_tensor(labels, dtype=torch.int64)

        target = {}
        target['boxes'] = boxes
        target['labels'] = labels
        target['image_id'] = torch.tensor([idx])

        # area and iscrowd are optional for simple training
        area = (boxes[:, 3] - boxes[:, 1]) * (boxes[:, 2] - boxes[:, 0])
        target['area'] = area
        target['iscrowd'] = torch.zeros((boxes.shape[0],), dtype=torch.int64)

        if self.transforms is not None:
            img = self.transforms(img)
        else:
            img = T.ToTensor()(img)

        return img, target


def collate_fn(batch):
    return tuple(zip(*batch))


def get_transform(train):
    transforms = []
    transforms.append(T.ToTensor())
    if train:
        # add simple horizontal flip augmentation
        transforms.append(T.RandomHorizontalFlip(0.5))
    return T.Compose(transforms)


def get_model(num_classes):
    # Load a model pre-trained on COCO
    model = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)

    # Get the number of input features for the classifier
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    # Replace the pre-trained head with a new one (note: +1 for background is handled by the library)
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model


def train_one_epoch(model, optimizer, data_loader, device, epoch, print_freq=100):
    model.train()
    lr_scheduler = None

    for i, (images, targets) in enumerate(tqdm(data_loader, desc=f"Epoch {epoch}")):
        images = list(img.to(device) for img in images)
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

        loss_dict = model(images, targets)
        losses = sum(loss for loss in loss_dict.values())

        optimizer.zero_grad()
        losses.backward()
        optimizer.step()

        if i % print_freq == 0:
            # print loss components
            loss_str = ", ".join([f"{k}: {v.item():.4f}" for k, v in loss_dict.items()])
            tqdm.write(f"Iter {i}: total_loss: {losses.item():.4f}, {loss_str}")


def evaluate_on_sample(model, device, image_path, output_path, threshold=0.5):
    model.eval()
    img = Image.open(image_path).convert("RGB")
    img_tensor = T.ToTensor()(img).to(device)
    with torch.no_grad():
        outputs = model([img_tensor])

    outputs = [{k: v.to('cpu') for k, v in t.items()} for t in outputs]
    boxes = outputs[0]['boxes'].numpy()
    scores = outputs[0]['scores'].numpy()
    labels = outputs[0]['labels'].numpy()

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for box, score, label in zip(boxes, scores, labels):
        if score < threshold:
            continue
        xmin, ymin, xmax, ymax = box
        draw.rectangle([xmin, ymin, xmax, ymax], outline=(255, 0, 0), width=2)
        text = f"{label}:{score:.2f}"
        if font:
            draw.text((xmin + 3, ymin + 3), text, fill=(255, 255, 255), font=font)
        else:
            draw.text((xmin + 3, ymin + 3), text, fill=(255, 255, 255))

    img.save(output_path)
    print(f"Saved inference result to {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description='Train Faster R-CNN on a CSV annotated dataset')
    parser.add_argument('--images', default='/ml_data/data_sets/car/data/training_images', help='images directory')
    parser.add_argument('--csv', default='/ml_data/data_sets/car/data/train_solution_bounding_boxes_with_label.csv', help='annotations CSV file')
    parser.add_argument('--num-classes', type=int, required=True, help='number of classes (including background)')
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--lr', type=float, default=0.005)
    parser.add_argument('--output', default='fasterrcnn_model.pth')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    return parser.parse_args()


def main():
    args = parse_args()
    device = torch.device(args.device)

    # dataset and dataloader
    dataset = CSVObjectDetectionDataset(args.images, args.csv, transforms=get_transform(train=True))
    dataset_test = CSVObjectDetectionDataset(args.images, args.csv, transforms=get_transform(train=False))

    # split dataset into train/test (simple split)
    indices = torch.randperm(len(dataset)).tolist()
    split = int(0.8 * len(indices))
    dataset = torch.utils.data.Subset(dataset, indices[:split])
    dataset_test = torch.utils.data.Subset(dataset_test, indices[split:])

    data_loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=4, collate_fn=collate_fn)
    data_loader_test = DataLoader(dataset_test, batch_size=1, shuffle=False, num_workers=4, collate_fn=collate_fn)

    model = get_model(args.num_classes)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=0.9, weight_decay=0.0005)

    # optional LR scheduler
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=3, gamma=0.1)

    for epoch in range(args.epochs):
        train_one_epoch(model, optimizer, data_loader, device, epoch, print_freq=50)
        lr_scheduler.step()

        # save intermediate checkpoint
        torch.save(model.state_dict(), f"{args.output}.epoch{epoch+1}")

    # final save
    torch.save(model.state_dict(), args.output)
    print(f"Model saved to {args.output}")

    # run inference on a few test images and save results
    # take up to 5 images from test set
    os.makedirs('inference_results', exist_ok=True)
    with torch.no_grad():
        model.eval()
        for i, (images, targets) in enumerate(data_loader_test):
            if i >= 5:
                break
            # images is a tuple of 1 image in this loader
            # get the original filename from dataset subsets
            # we don't have direct filename access here, so just save indexed files
            image_tensor = images[0]
            img_pil = T.ToPILImage()(image_tensor)
            tmp_in = 'tmp_infer_input.jpg'
            img_pil.save(tmp_in)
            out_path = f'inference_results/result_{i+1}.jpg'
            evaluate_on_sample(model, device, tmp_in, out_path, threshold=0.5)


if __name__ == '__main__':
    main()
