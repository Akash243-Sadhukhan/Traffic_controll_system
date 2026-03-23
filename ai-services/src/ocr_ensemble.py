
import asyncio
import cv2
import numpy as np
import torch
import easyocr
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from collections import Counter

class OcrEnsemble:
    """
    An ensemble model for OCR that combines EasyOCR and Microsoft TrOCR.

    This class runs both models in parallel on a given image and combines their
    results using a weighted confidence score and character-level voting for
    more accurate text recognition.
    """
    def __init__(self, easyocr_weight=0.4, trocr_weight=0.6):
        """
        Initializes the ensemble by loading and caching the OCR models.
        """
        self.device = 'mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"OCR Ensemble using device: {self.device}")

        # 1. Initialize EasyOCR
        self.easyocr_reader = easyocr.Reader(['en'], gpu=(self.device != 'cpu'))

        # 2. Initialize TrOCR (and cache it)
        self.trocr_processor = None
        self.trocr_model = None
        try:
            self.trocr_processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten')
            self.trocr_model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten').to(self.device)
            print("TrOCR model loaded successfully.")
        except Exception as e:
            print(f"Warning: Could not load TrOCR model. Falling back to EasyOCR only. Error: {e}")

        # 3. Set weights for ensemble
        self.easyocr_weight = easyocr_weight
        self.trocr_weight = trocr_weight

    async def run_easyocr(self, image_crop):
        """
        Asynchronously runs EasyOCR on the image crop.
        Returns:
            A tuple (text, confidence_score) or (None, 0) on failure.
        """
        try:
            # EasyOCR's readtext is blocking, run it in an executor
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, self.easyocr_reader.readtext, image_crop, False, 1.5
            )
            
            if not results:
                return None, 0

            # Combine results and calculate average confidence
            text = " ".join([res[1] for res in results])
            confidence = np.mean([res[2] for res in results]) if results else 0
            return text, confidence
        except Exception as e:
            print(f"EasyOCR failed: {e}")
            return None, 0

    async def run_trocr(self, image_crop):
        """
        Asynchronously runs TrOCR on the image crop.
        Returns:
            A tuple (text, confidence_score) or (None, 0) on failure.
        """
        if self.trocr_model is None or self.trocr_processor is None:
            return None, 0
        
        try:
            # TrOCR is not thread-safe with MPS, so ensure it runs in the main thread context if needed
            # For asyncio, we assume it's managed correctly.
            pixel_values = self.trocr_processor(images=image_crop, return_tensors="pt").pixel_values.to(self.device)
            
            # Generate token IDs and include scores
            output = self.trocr_model.generate(pixel_values, output_scores=True, return_dict_in_generate=True)
            generated_ids = output.sequences
            
            # Decode the token IDs to text
            generated_text = self.trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

            # Calculate confidence score from logits
            scores = output.scores
            token_probs = [torch.softmax(s, dim=-1).max().item() for s in scores]
            confidence = np.mean(token_probs) if token_probs else 0

            return generated_text, confidence
        except Exception as e:
            print(f"TrOCR failed: {e}")
            return None, 0

    def _char_level_voting(self, easy_text, trocr_text, easy_conf, trocr_conf):
        """
        Performs character-level voting if confidence scores are close.
        """
        easy_text = easy_text.replace(" ", "").upper()
        trocr_text = trocr_text.replace(" ", "").upper()
        
        max_len = max(len(easy_text), len(trocr_text))
        final_text = []

        for i in range(max_len):
            easy_char = easy_text[i] if i < len(easy_text) else ''
            trocr_char = trocr_text[i] if i < len(trocr_text) else ''

            if easy_char == trocr_char:
                final_text.append(easy_char)
            elif not easy_char:
                final_text.append(trocr_char)
            elif not trocr_char:
                final_text.append(easy_char)
            else:
                # If characters differ, pick the one from the higher-confidence model
                if trocr_conf > easy_conf:
                    final_text.append(trocr_char)
                else:
                    final_text.append(easy_char)
        
        return "".join(final_text)

    async def recognize(self, image_crop):
        """
        Performs parallel OCR and returns the ensembled result.
        """
        # Preprocess image once for both models
        gray = cv2.cvtColor(image_crop, cv2.COLOR_BGR2GRAY)
        
        # Run both OCR tasks concurrently
        easy_task = self.run_easyocr(gray)
        trocr_task = self.run_trocr(image_crop) # TrOCR prefers color images
        
        results = await asyncio.gather(easy_task, trocr_task, return_exceptions=True)

        easy_res, trocr_res = results
        
        # Handle exceptions during task execution
        if isinstance(easy_res, Exception):
            print(f"EasyOCR task raised an exception: {easy_res}")
            easy_text, easy_conf = None, 0
        else:
            easy_text, easy_conf = easy_res

        if isinstance(trocr_res, Exception):
            print(f"TrOCR task raised an exception: {trocr_res}")
            trocr_text, trocr_conf = None, 0
        else:
            trocr_text, trocr_conf = trocr_res

        # If TrOCR failed or is unavailable, fall back to EasyOCR
        if not trocr_text or self.trocr_model is None:
            return easy_text if easy_text else ""

        # If EasyOCR failed, use TrOCR
        if not easy_text:
            return trocr_text

        # --- Ensemble Logic ---
        weighted_easy = easy_conf * self.easyocr_weight
        weighted_trocr = trocr_conf * self.trocr_weight

        # If scores are not close, return the higher-confidence result
        if abs(weighted_easy - weighted_trocr) > 0.1:
            if weighted_trocr > weighted_easy:
                return trocr_text
            else:
                return easy_text
        else:
            # If scores are close, perform character-level voting
            return self._char_level_voting(easy_text, trocr_text, easy_conf, trocr_conf)

def run_recognition(ensemble, image_path):
    """Helper function to test the ensemble with a single image."""
    async def main():
        image = cv2.imread(image_path)
        if image is None:
            print("Failed to load image.")
            return
        
        result = await ensemble.recognize(image)
        print(f"Ensemble Result: {result}")

    asyncio.run(main())

if __name__ == '__main__':
    # This is for testing the module independently.
    # You would need an image file named 'test_plate.jpg' in the same directory.
    print("Running OCR Ensemble Test...")
    ocr_ensemble = OcrEnsemble()
    test_image_path = 'test_plate.jpg' # Make sure you have a test image
    if cv2.imread(test_image_path) is not None:
        run_recognition(ocr_ensemble, test_image_path)
    else:
        print(f"Test image '{test_image_path}' not found. Skipping standalone test.")
