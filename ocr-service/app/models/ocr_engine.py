"""
PaddleOCR Engine Wrapper
Encapsulates PaddleOCR initialization and processing logic
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class OCREngine:
    """
    PaddleOCR engine wrapper
    Initializes OCR engine once and reuses across requests
    """

    def __init__(self, use_gpu: Optional[bool] = None, lang: str = "ch"):
        """
        Initialize PaddleOCR engine

        Args:
            use_gpu: Enable GPU acceleration (None = auto-detect, True = force GPU, False = force CPU)
            lang: Language code (default: "ch" for Chinese-English mixed)
                Common codes: "ch" (Chinese-English), "en" (English only),
                "chinese_cht" (Traditional Chinese), "japan", "korean", etc.
                See PaddleOCR docs for full list
        """
        self.lang = lang
        self.ocr = None
        self._initialized = False
        self._gpu_available = None
        self.use_gpu = self._detect_gpu(use_gpu)

    def _detect_gpu(self, use_gpu: Optional[bool]) -> bool:
        """
        Auto-detect GPU availability

        Args:
            use_gpu: User preference (None = auto, True = force GPU, False = force CPU)

        Returns:
            Whether to use GPU
        """
        if use_gpu is False:
            return False
        if use_gpu is True:
            return True

        import platform
        system = platform.system()
        machine = platform.machine()

        if system == "Darwin":
            logger.info("macOS detected: PaddlePaddle does not support GPU on macOS (no Metal support), using CPU")
            self._gpu_available = False
            return False

        try:
            import paddle
            if hasattr(paddle, 'device') and paddle.device.is_compiled_with_cuda():
                try:
                    paddle.device.set_device('gpu')
                    self._gpu_available = True
                    logger.info("NVIDIA GPU detected and available")
                    return True
                except Exception:
                    logger.warning("GPU compiled but not available, falling back to CPU")
                    self._gpu_available = False
                    return False
            else:
                logger.info("GPU not compiled in PaddlePaddle, using CPU")
                self._gpu_available = False
                return False
        except ImportError:
            logger.warning("PaddlePaddle not installed yet, will auto-detect during initialization")
            return False
        except Exception as e:
            logger.warning(f"GPU detection failed: {e}, falling back to CPU")
            self._gpu_available = False
            return False

    def _initialize(self):
        """Lazy initialization of PaddleOCR"""
        if self._initialized:
            return

        try:
            from paddleocr import PaddleOCR

            logger.info(f"Initializing PaddleOCR (GPU: {self.use_gpu}, Lang: {self.lang})")

            try:
                self.ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang=self.lang,
                    use_gpu=self.use_gpu,
                    show_log=False
                )
                self._initialized = True
                logger.info(f"PaddleOCR initialized successfully (GPU: {self.use_gpu})")
            except Exception as gpu_error:
                if self.use_gpu:
                    logger.warning(f"GPU initialization failed: {gpu_error}, retrying with CPU")
                    self.use_gpu = False
                    self.ocr = PaddleOCR(
                        use_angle_cls=True,
                        lang=self.lang,
                        use_gpu=False,
                        show_log=False
                    )
                    self._initialized = True
                    logger.info("PaddleOCR initialized with CPU fallback")
                else:
                    raise

        except ImportError:
            logger.error("PaddleOCR not installed. Install with: pip install paddleocr")
            raise Exception("PaddleOCR library not available")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            raise

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process single image file

        Args:
            image_path: Path to image file

        Returns:
            Dict containing:
                - text: Full extracted text
                - blocks: List of text blocks with confidence and bbox
                - page: Page number (always 1 for images)
        """
        self._initialize()

        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        try:
            result = self.ocr.ocr(image_path, cls=True)

            if not result or not result[0]:
                return {
                    "text": "",
                    "blocks": [],
                    "page": 1
                }

            blocks = []
            text_parts = []

            for line in result[0]:
                if not line:
                    continue

                bbox, (text, confidence) = line
                blocks.append({
                    "text": text,
                    "confidence": float(confidence),
                    "bbox": [float(coord) for coord in bbox]
                })
                text_parts.append(text)

            full_text = "\n".join(text_parts)

            return {
                "text": full_text,
                "blocks": blocks,
                "page": 1
            }

        except Exception as e:
            logger.error(f"OCR processing failed for {image_path}: {e}")
            raise

    def process_pdf(self, pdf_path: str, dpi: int = 300) -> Dict[str, Any]:
        """
        Process PDF file (convert to images and process each page)

        Args:
            pdf_path: Path to PDF file
            dpi: DPI for PDF to image conversion (default: 300)

        Returns:
            Dict containing:
                - pages: List of page results
        """
        self._initialize()

        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            from pdf2image import convert_from_path

            logger.info(f"Converting PDF to images: {pdf_path} (DPI: {dpi})")
            images = convert_from_path(pdf_path, dpi=dpi)

            pages = []
            for page_num, image in enumerate(images, start=1):
                logger.info(f"Processing PDF page {page_num}/{len(images)}")

                # Save temporary image
                temp_image_path = f"/tmp/pdf_page_{page_num}.png"
                image.save(temp_image_path, "PNG")

                try:
                    page_result = self.process_image(temp_image_path)
                    page_result["page"] = page_num
                    pages.append(page_result)
                finally:
                    # Clean up temporary image
                    if Path(temp_image_path).exists():
                        os.remove(temp_image_path)

            return {
                "pages": pages,
                "total_pages": len(pages)
            }

        except ImportError:
            logger.error("pdf2image not installed. Install with: pip install pdf2image")
            raise Exception("PDF processing library not available")
        except Exception as e:
            logger.error(f"PDF OCR processing failed for {pdf_path}: {e}")
            raise

    def check_gpu_available(self) -> bool:
        """
        Check if GPU is available for PaddleOCR

        Returns:
            True if GPU is available, False otherwise
        """
        if self._gpu_available is not None:
            return self._gpu_available

        try:
            import paddle
            if hasattr(paddle, 'device') and paddle.device.is_compiled_with_cuda():
                try:
                    paddle.device.set_device('gpu')
                    self._gpu_available = True
                    return True
                except Exception:
                    self._gpu_available = False
                    return False
            else:
                self._gpu_available = False
                return False
        except Exception:
            self._gpu_available = False
            return False




