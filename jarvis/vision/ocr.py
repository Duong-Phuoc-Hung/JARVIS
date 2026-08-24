"""
jarvis/vision/ocr.py
====================
Desktop Optical Character Recognition (OCR) Engine.
Extracts on-screen text with dual-tier fallback:
  1. Local Pytesseract OCR (Fast, offline, zero-token cost)
  2. Cloud Vision LLM OCR (Accurate handwritten/stylized text extraction)
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Optional, Tuple, Union

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    PIL_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    PYTESSERACT_AVAILABLE = False

from jarvis.vision.screen import ScreenVisionManager

logger = logging.getLogger("jarvis.vision.ocr")


class DesktopOCR:
    """
    Unified Desktop Text Recognition Engine.
    Executes local Tesseract OCR with automatic fallback to Vision LLM.
    """

    def __init__(
        self,
        vision_manager: Optional[ScreenVisionManager] = None,
        default_lang: str = "eng+vie",
    ) -> None:
        self.vision_manager = vision_manager or ScreenVisionManager()
        self.default_lang = default_lang
        self._tesseract_tested = False
        self._tesseract_functional = False

    def is_tesseract_available(self) -> bool:
        """Checks if local pytesseract module and tesseract binary are available."""
        if not PYTESSERACT_AVAILABLE or pytesseract is None:
            return False

        if not self._tesseract_tested:
            try:
                # Test minimal OCR on synthetic image
                if PIL_AVAILABLE and Image is not None:
                    dummy = Image.new("RGB", (30, 30), color="white")
                    _ = pytesseract.image_to_string(dummy)
                    self._tesseract_functional = True
                else:
                    self._tesseract_functional = False
            except Exception:
                self._tesseract_functional = False
            self._tesseract_tested = True

        return self._tesseract_functional

    def extract_text(
        self,
        image_input: Union[bytes, Any, str],
        lang: Optional[str] = None,
    ) -> str:
        """
        Extracts plain text from image bytes, PIL Image, or file path.
        Uses Pytesseract if available; falls back to Vision LLM.
        """
        selected_lang = lang or self.default_lang
        img = self._load_image(image_input)

        # 1. Tier 1: Local Pytesseract OCR
        if self.is_tesseract_available() and img is not None:
            try:
                text = pytesseract.image_to_string(img, lang=selected_lang).strip()
                if text:
                    return text
                # Try single lang fallback
                if "+" in selected_lang:
                    single_lang = selected_lang.split("+")[0]
                    text = pytesseract.image_to_string(img, lang=single_lang).strip()
                    if text:
                        return text
            except Exception as exc:
                logger.debug("Pytesseract failed, falling back to Vision LLM OCR: %s", exc)

        # 2. Tier 2: Vision LLM OCR Fallback
        raw_bytes = self._get_image_bytes(image_input, img)
        if raw_bytes:
            prompt = "Hãy trích xuất và đọc chính xác toàn bộ văn bản có trong hình ảnh này. Chỉ trả về phần văn bản trích xuất được."
            result = self.vision_manager.analyze_screen(query=prompt, image_bytes=raw_bytes)
            return result.strip()

        return ""

    def extract_text_from_screen(self, roi: Optional[Tuple[int, int, int, int]] = None) -> str:
        """
        Captures the screen (or ROI) and extracts all visible text.
        """
        raw_bytes, _ = self.vision_manager.capture_screenshot(max_dim=1920, roi=roi)
        return self.extract_text(raw_bytes)

    def _load_image(self, image_input: Union[bytes, Any, str]) -> Optional[Any]:
        """Normalizes various input formats into a PIL Image object."""
        if not PIL_AVAILABLE or Image is None:
            return None

        try:
            if isinstance(image_input, Image.Image):
                return image_input
            elif isinstance(image_input, (bytes, bytearray)):
                return Image.open(io.BytesIO(image_input))
            elif isinstance(image_input, (str, Path)):
                return Image.open(str(image_input))
        except Exception as exc:
            logger.debug("Failed to load image for OCR: %s", exc)

        return None

    def _get_image_bytes(self, image_input: Union[bytes, Any, str], loaded_img: Optional[Any]) -> Optional[bytes]:
        """Converts image input to JPEG bytes for Vision LLM payload."""
        if isinstance(image_input, (bytes, bytearray)):
            return bytes(image_input)

        if loaded_img is not None:
            buf = io.BytesIO()
            loaded_img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()

        return None
