"""
EasyOCR Engine Wrapper
Encapsulates EasyOCR initialization and processing logic.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class OCREngine:
    """
    EasyOCR engine wrapper.
    Initializes OCR engine once and reuses across requests.
    """

    def __init__(self, use_gpu: Optional[bool] = None, lang: str = "ch"):
        """
        Initialize EasyOCR engine.

        Args:
            use_gpu: Enable GPU acceleration (None = auto-detect)
            lang: Language code — maps to EasyOCR language list
        """
        self.lang = lang
        self.reader = None
        self._initialized = False
        self._gpu_available = None
        self.use_gpu = self._detect_gpu(use_gpu)

    def _detect_gpu(self, use_gpu: Optional[bool]) -> bool:
        """Auto-detect GPU availability via PyTorch."""
        if use_gpu is False:
            return False
        if use_gpu is True:
            return True
        try:
            import torch
            available = torch.cuda.is_available()
            if available:
                logger.info("CUDA GPU detected")
            else:
                logger.info("No GPU available, using CPU")
            return available
        except Exception as e:
            logger.warning("GPU detection failed: %s, using CPU", e)
            return False

    @staticmethod
    def _map_languages(lang: str) -> List[str]:
        """Map internal language code to EasyOCR language list."""
        mapping = {
            "ch": ["ch_tra", "en"],          # Traditional Chinese + English
            "ch_sim": ["ch_sim", "en"],       # Simplified Chinese + English
            "en": ["en"],                     # English only
            "japan": ["ja", "en"],            # Japanese + English
            "korean": ["ko", "en"],           # Korean + English
        }
        return mapping.get(lang, ["ch_tra", "en"])

    def _initialize(self):
        """Lazy initialization of EasyOCR reader."""
        if self._initialized:
            return

        try:
            import easyocr

            langs = self._map_languages(self.lang)
            logger.info("Initializing EasyOCR with languages: %s (gpu=%s)", langs, self.use_gpu)

            self.reader = easyocr.Reader(
                langs,
                gpu=self.use_gpu,
                verbose=False,
            )

            self._initialized = True
            logger.info("EasyOCR initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize EasyOCR: %s", e)
            raise

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process single image file.

        Args:
            image_path: Path to image file

        Returns:
            Dict with text, blocks (bbox + text + confidence), page number
        """
        self._initialize()

        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        try:
            # EasyOCR returns list of (bbox, text, confidence)
            results = self.reader.readtext(image_path)

            blocks = []
            text_parts = []

            for bbox, text, confidence in results:
                if not text.strip():
                    continue
                
                # Convert bbox coordinates from numpy.int32 to native Python int
                clean_bbox = [[int(coord) for coord in point] for point in bbox]
                
                blocks.append({
                    "text": text,
                    "confidence": float(confidence),
                    "bbox": clean_bbox,
                })
                text_parts.append(text)

            full_text = "\n".join(text_parts)
            logger.info(
                "EasyOCR extracted %d text blocks from %s: %s",
                len(blocks), image_path,
                full_text[:200] + "..." if len(full_text) > 200 else full_text,
            )

            return {"text": full_text, "blocks": blocks, "page": 1}

        except Exception as e:
            logger.exception("OCR processing failed for %s", image_path)
            raise

    def process_pdf(self, pdf_path: str, dpi: int = 300) -> Dict[str, Any]:
        """
        Process PDF file (convert to images and OCR each page).
        """
        self._initialize()

        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            from pdf2image import convert_from_path

            logger.info("Converting PDF to images: %s (DPI: %d)", pdf_path, dpi)
            images = convert_from_path(pdf_path, dpi=dpi)

            pages = []
            for page_num, image in enumerate(images, start=1):
                temp_path = f"/tmp/pdf_page_{page_num}.png"
                image.save(temp_path, "PNG")
                try:
                    page_result = self.process_image(temp_path)
                    page_result["page"] = page_num
                    pages.append(page_result)
                finally:
                    if Path(temp_path).exists():
                        os.remove(temp_path)

            return {"pages": pages, "total_pages": len(pages)}

        except Exception as e:
            logger.error("PDF OCR failed for %s: %s", pdf_path, e)
            raise

    def check_gpu_available(self) -> bool:
        """Check if GPU is available."""
        if self._gpu_available is not None:
            return self._gpu_available
        try:
            import torch
            self._gpu_available = torch.cuda.is_available()
            return self._gpu_available
        except Exception:
            self._gpu_available = False
            return False
