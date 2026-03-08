"""
Faster R-CNN object detection training + inference script (PyTorch + torchvision)

This file was updated to handle environments where PyTorch is NOT installed.
Behavior:
- If `torch` is available: runs the original training + inference using Faster R-CNN.
- If `torch` is NOT available: the script will *not* crash. Instead it will:
  1) print clear installation instructions for PyTorch,
  2) provide a "demo" mode that generates a small synthetic dataset (images + CSV),
  3) run a *dataset validation / simulation* pass that draws the ground-truth boxes from
     the CSV onto images and saves them in `inference_results/` so you can validate your
     annotations and pipeline without PyTorch installed.

Usage examples:
- To run on your dataset:
    python fasterrcnn_pytorch_object_detection.py --images images/ --csv annotations.csv --num-classes 3

- To run a self-contained demo (creates synthetic images + CSV and runs in available mode):
    python fasterrcnn_pytorch_object_detection.py --demo

Notes:
- If you see `ModuleNotFoundError: No module named 'torch'`, run the printed install commands (CPU or CUDA) on your machine.
- This script intentionally does not attempt to install packages itself; that must be done by the environment / user.
"""


"""sumary_line

Keyword arguments:
argument -- run -- "python3 obd.py --num-class 3"

*********** THE --device IS SET TO "MPS" FOR RUNNING IN MAC SET IT TO "CUDA" OR "CPU" ACCORDING TO YOUR DEVICE AND THE CODE **********
                    NOTES:
                    THE CODE HAS LOT OF ERRORS.
                    DEBUG IT YOURSELF.
"""


import argparse
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pandas as pd
from tqdm import tqdm

# Try to import torch and torchvision. If unavailable, fall back to simulation mode.
TORCH_AVAILABLE = True
try:
    import torch
    from torch.utils.data import Dataset, DataLoader
    import torchvision
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
    # torchvision transforms may or may not be present; guard uses later
    try:
        import torchvision.transforms as T
        TORCH_TF_AVAILABLE = True
    except Exception:
        TORCH_TF_AVAILABLE = False
except ModuleNotFoundError:
    TORCH_AVAILABLE = False
    TORCH_TF_AVAILABLE = False


def print_install_instructions():
    print("\nPyTorch appears to be missing in this environment (ModuleNotFoundError: No module named 'torch').")
    print("If you are running this code locally you can install PyTorch. Common installation commands:\n")
    print("1) CPU-only wheel (pip) -- fast and works on most machines:")
    print("   python -m pip install --upgrade pip")
    print("   python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu")
    print("")
    print("2) CUDA-enabled install (example for CUDA 11.8) -- only if you have compatible NVIDIA drivers:")
    print("   python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    print("")
    print("3) Conda (alternative):")
    print("   conda install pytorch torchvision torchaudio cpuonly -c pytorch")
    print("")
    print("For the most up-to-date install commands and CUDA options, visit https://pytorch.org/get-started/locally\n")


class CSVObjectDetectionDataset:
    """A minimal dataset wrapper that reads a CSV with annotations.

    CSV must have these columns: filename,xmin,ymin,xmax,ymax,label
    Multiple rows may refer to the same image.

    This class returns: (PIL.Image, target_dict)
    where target_dict contains 'boxes' as an (N,4) numpy array and 'labels' as (N,) int array.
    """

    def __init__(self, images_dir, annotations_csv):
        self.images_dir = images_dir
        if not os.path.exists(annotations_csv):
            raise FileNotFoundError(f"Annotations CSV not found: {annotations_csv}")
        self.annotations = pd.read_csv(annotations_csv)
        required_cols = {'filename', 'xmin', 'ymin', 'xmax', 'ymax', 'label'}
        if not required_cols.issubset(set(self.annotations.columns)):
            raise ValueError(f"CSV must contain columns: {required_cols}. Found: {self.annotations.columns.tolist()}")

        grouped = self.annotations.groupby('filename')
        self.image_files = list(grouped.groups.keys())
        self.annotations_groups = {fname: grouped.get_group(fname) for fname in self.image_files}

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, idx):
        fname = self.image_files[idx]
        img_path = os.path.join(self.images_dir, fname)
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Image file not found: {img_path}")
        img = Image.open(img_path).convert('RGB')

        ann = self.annotations_groups[fname]
        boxes = ann[['xmin', 'ymin', 'xmax', 'ymax']].values.astype(np.float32)
        labels = ann['label'].values.astype(np.int64)

        target = {'boxes': boxes, 'labels': labels, 'filename': fname}
        return img, target


def collate_fn(batch):
    # batch: list of (img, target)
    imgs = [b[0] for b in batch]
    targets = [b[1] for b in batch]
    return imgs, targets


# The original transform logic relied on torchvision. We'll convert PIL->tensor during batch prep
# when torch is available.


def get_model(num_classes):
    if not TORCH_AVAILABLE:
        raise RuntimeError("get_model() should only be called when torch is available")

    # prefer new weights API when available, but be robust to different torchvision versions
    try:
        weights = torchvision.models.detection.FasterRCNN_ResNet50_FPN_Weights.DEFAULT
        model = torchvision.models.detection.fasterrcnn_resnet50_fpn(weights=weights)
    except Exception:
        # fallback to older API
        model = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)

    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model


def prepare_batch_for_torch(images_pil, targets, device):
    """Convert list of PIL images and target dicts into torch tensors suitable for torchvision models."""
    assert TORCH_AVAILABLE, "PyTorch required for prepare_batch_for_torch"

    images_t = []
    targets_t = []

    for idx, (img_pil, t) in enumerate(zip(images_pil, targets)):
        # convert image -> tensor
        if TORCH_TF_AVAILABLE:
            img_t = T.ToTensor()(img_pil).to(device)
        else:
            arr = np.array(img_pil).astype(np.float32) / 255.0
            # H,W,C -> C,H,W
            import torch as _torch
            img_t = _torch.from_numpy(arr).permute(2, 0, 1).to(device)

        boxes = torch.tensor(t['boxes'], dtype=torch.float32).to(device)
        labels = torch.tensor(t['labels'], dtype=torch.int64).to(device)
        target_t = {'boxes': boxes, 'labels': labels, 'image_id': torch.tensor([idx])}

        images_t.append(img_t)
        targets_t.append(target_t)

    return images_t, targets_t


def train_one_epoch(model, optimizer, data_loader, device, epoch, print_freq=100):
    model.train()
    for i, (images_pil, targets) in enumerate(tqdm(data_loader, desc=f"Epoch {epoch}")):
        images, targets_t = prepare_batch_for_torch(images_pil, targets, device)

        loss_dict = model(images, targets_t)
        losses = sum(loss for loss in loss_dict.values())

        optimizer.zero_grad()
        losses.backward()
        optimizer.step()

        if i % print_freq == 0:
            loss_str = ", ".join([f"{k}: {v.item():.4f}" for k, v in loss_dict.items()])
            tqdm.write(f"Iter {i}: total_loss: {losses.item():.4f}, {loss_str}")


def evaluate_with_model(model, device, image_pil, output_path, threshold=0.5):
    """Run the model on a single PIL image and save drawn detections."""
    model.eval()
    img_tensor = (T.ToTensor()(image_pil).to(device)) if TORCH_TF_AVAILABLE else torch.from_numpy(np.array(image_pil).astype(np.float32)/255.0).permute(2,0,1).to(device)
    with torch.no_grad():
        outputs = model([img_tensor])
    outputs = [{k: v.to('cpu') for k, v in t.items()} for t in outputs]

    boxes = outputs[0].get('boxes', torch.empty((0,4))).numpy()
    scores = outputs[0].get('scores', torch.empty((0,))).numpy()
    labels = outputs[0].get('labels', torch.empty((0,), dtype=torch.int64)).numpy()

    draw = ImageDraw.Draw(image_pil)
    font = ImageFont.load_default()

    for box, score, label in zip(boxes, scores, labels):
        if score < threshold:
            continue
        xmin, ymin, xmax, ymax = box.tolist()
        draw.rectangle([xmin, ymin, xmax, ymax], outline=(255, 0, 0), width=2)
        draw.text((xmin + 3, ymin + 3), f"{label}:{score:.2f}", fill=(255,255,255), font=font)

    image_pil.save(output_path)


def draw_ground_truth_on_image(image_pil, boxes, labels, output_path):
    draw = ImageDraw.Draw(image_pil)
    font = ImageFont.load_default()
    for box, label in zip(boxes, labels):
        xmin, ymin, xmax, ymax = map(float, box)
        draw.rectangle([xmin, ymin, xmax, ymax], outline=(0,255,0), width=2)
        draw.text((xmin + 3, ymin + 3), f"gt:{label}", fill=(255,255,255), font=font)
    image_pil.save(output_path)


def create_demo_dataset(out_dir='demo_images', csv_path='demo_annotations.csv', n_images=3):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for i in range(n_images):
        w, h = 640, 480
        img = Image.new('RGB', (w, h), color=(50 + i*30, 80 + i*20, 120 + i*10))
        draw = ImageDraw.Draw(img)
        # create 1-3 rectangles per image
        num_boxes = 1 + (i % 3)
        for b in range(num_boxes):
            xmin = 30 + b*80
            ymin = 40 + b*60
            xmax = xmin + 120
            ymax = ymin + 90
            draw.rectangle([xmin, ymin, xmax, ymax], outline=(255,255,0), width=4)
            rows.append({'filename': f'image_{i+1}.jpg', 'xmin': xmin, 'ymin': ymin, 'xmax': xmax, 'ymax': ymax, 'label': 1})
        img_path = os.path.join(out_dir, f'image_{i+1}.jpg')
        img.save(img_path)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    print(f"Created demo images in {out_dir} and annotations {csv_path}")
    return out_dir, csv_path


def parse_args():
    parser = argparse.ArgumentParser(description='Train/validate Faster R-CNN on a CSV annotated dataset')
    parser.add_argument('--images', default='/Users/akash/Documents/python/ml_data/data_sets/car/data/training_images',help='images directory')
    parser.add_argument('--csv', default='/Users/akash/Documents/python/ml_data/data_sets/car/data/train_solution_bounding_boxes_with_label.csv', help='annotations CSV file')
    parser.add_argument('--num-classes', type=int, help='number of classes (including background)')
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--lr', type=float, default=0.005)
    parser.add_argument('--output', default='fasterrcnn_model.pth')
    parser.add_argument('--device', default='mps', help='device string, e.g. cpu or cuda')
    parser.add_argument('--demo', action='store_true', help='create and run a small demo dataset')
    return parser.parse_args()


def main():
    args = parse_args()

    if args.demo:
        demo_images_dir, demo_csv = create_demo_dataset()
        args.images = demo_images_dir
        args.csv = demo_csv
        args.num_classes = args.num_classes or 2

    if not args.images or not args.csv:
        print("Error: --images and --csv are required unless --demo is used. Run with --help for usage.")
        sys.exit(1)

    # If torch isn't available, inform the user and run the dataset validation + visualization pass.
    if not TORCH_AVAILABLE:
        print_install_instructions()
        print("Running annotation validation + visualization (no model will be trained because torch is missing).\n")

        dataset = CSVObjectDetectionDataset(args.images, args.csv)
        os.makedirs('inference_results', exist_ok=True)

        for i in range(min(len(dataset), 10)):
            img_pil, target = dataset[i]
            out_path = os.path.join('inference_results', f'result_{i+1}.jpg')
            draw_ground_truth_on_image(img_pil, target['boxes'], target['labels'], out_path)
            print(f"Wrote {out_path} (drawn ground-truth)")

        print("\nDone. Inspect inference_results/ to verify your images and CSV annotations.")
        return

    # Torch is available, proceed with regular training workflow
    device = torch.device(args.device if args.device else ('cuda' if torch.cuda.is_available() else 'cpu'))
    print(f"Using device: {device}")

    dataset = CSVObjectDetectionDataset(args.images, args.csv)

    # simple deterministic split
    n = len(dataset)
    if n == 0:
        print("No images found in the dataset. Exiting.")
        return
    indices = list(range(n))
    split = int(0.8 * n)
    train_indices = indices[:split]
    test_indices = indices[split:]

    from torch.utils.data import Subset
    train_set = Subset(dataset, train_indices)
    test_set = Subset(dataset, test_indices)

    data_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=0, collate_fn=collate_fn)
    data_loader_test = DataLoader(test_set, batch_size=1, shuffle=False, num_workers=0, collate_fn=collate_fn)

    model = get_model(args.num_classes)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=0.9, weight_decay=0.0005)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=3, gamma=0.1)

    for epoch in range(args.epochs):
        train_one_epoch(model, optimizer, data_loader, device, epoch, print_freq=10)
        lr_scheduler.step()
        torch.save(model.state_dict(), f"{args.output}.epoch{epoch+1}")
        print(f"Saved checkpoint: {args.output}.epoch{epoch+1}")

    torch.save(model.state_dict(), args.output)
    print(f"Model saved to {args.output}")

    # run inference on a few test images and save results
    os.makedirs('inference_results', exist_ok=True)
    model.eval()
    with torch.no_grad():
        for i, (images_pil, targets) in enumerate(data_loader_test):
            if i >= 5:
                break
            img_pil = images_pil[0]
            out_path = os.path.join('inference_results', f'result_{i+1}.jpg')
            evaluate_with_model(model, device, img_pil, out_path, threshold=0.5)
            print(f"Wrote {out_path}")


if __name__ == '__main__':
    main()
