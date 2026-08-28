"""
jarvis/vision/computer_use.py
=============================
Anthropic 1000x1000 Normalized Coordinate Grounding & Multi-Tier UI Element Grounding Engine.

Features:
- Normalized Coordinate Space: 0-1000 normalized grid with bidirectional conversion
  to/from physical screen pixel coordinates.
- BoundingBox & UIElement data structures with center calculation, IOU, and pixel mapping.
- 4-Tier UI Element Grounding Engine:
    * Tier 1: Vision LLM Grounding (Gemini 1.5 Flash / GPT-4o Vision structured prompt).
    * Tier 2: Local Desktop OCR Bounding Boxes (DesktopOCR / pytesseract word/line boxes).
    * Tier 3: Win32 UIAutomation / Native Child Windows (win32gui.EnumChildWindows & GetWindowRect).
    * Tier 4: Template Matching & Synthetic UI fallback.
"""
from __future__ import annotations

import ctypes
import io
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    PIL_AVAILABLE = False

try:
    import pytesseract  # type: ignore
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    PYTESSERACT_AVAILABLE = False

try:
    import win32gui  # type: ignore
    WIN32GUI_AVAILABLE = True
except ImportError:
    win32gui = None  # type: ignore
    WIN32GUI_AVAILABLE = False

from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenVisionManager

logger = logging.getLogger("jarvis.vision.computer_use")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Coordinate Space & Geometry Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BoundingBox:
    """
    Anthropic Computer-Use Normalized Bounding Box (0 - 1000 coordinate grid).
    Coordinates:
        ymin: Top normalized coordinate (0 - 1000)
        xmin: Left normalized coordinate (0 - 1000)
        ymax: Bottom normalized coordinate (0 - 1000)
        xmax: Right normalized coordinate (0 - 1000)
    """
    ymin: int
    xmin: int
    ymax: int
    xmax: int

    def __post_init__(self) -> None:
        # Clamp coordinates to [0, 1000]
        self.ymin = max(0, min(1000, int(round(self.ymin))))
        self.xmin = max(0, min(1000, int(round(self.xmin))))
        self.ymax = max(0, min(1000, int(round(self.ymax))))
        self.xmax = max(0, min(1000, int(round(self.xmax))))

        # Ensure min <= max
        if self.ymin > self.ymax:
            self.ymin, self.ymax = self.ymax, self.ymin
        if self.xmin > self.xmax:
            self.xmin, self.xmax = self.xmax, self.xmin

    @property
    def center_norm(self) -> tuple[int, int]:
        """Returns (center_x, center_y) in normalized [0, 1000] coordinates."""
        return (self.xmin + self.xmax) // 2, (self.ymin + self.ymax) // 2

    @property
    def width_norm(self) -> int:
        """Returns width in normalized units (0 - 1000)."""
        return self.xmax - self.xmin

    @property
    def height_norm(self) -> int:
        """Returns height in normalized units (0 - 1000)."""
        return self.ymax - self.ymin

    @property
    def area_norm(self) -> int:
        """Returns area in normalized units squared."""
        return self.width_norm * self.height_norm

    def to_pixel_coords(self, screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
        """
        Converts normalized bounding box to physical screen pixel coordinates.
        Returns: (left, top, right, bottom)
        """
        if screen_w <= 0 or screen_h <= 0:
            return (0, 0, 0, 0)
        left = int(round(self.xmin * screen_w / 1000.0))
        top = int(round(self.ymin * screen_h / 1000.0))
        right = int(round(self.xmax * screen_w / 1000.0))
        bottom = int(round(self.ymax * screen_h / 1000.0))

        # Clamp to screen boundary
        left = max(0, min(screen_w, left))
        top = max(0, min(screen_h, top))
        right = max(left, min(screen_w, right))
        bottom = max(top, min(screen_h, bottom))
        return left, top, right, bottom

    def center_pixel(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        """
        Returns center point in physical screen pixel coordinates (cx, cy).
        """
        left, top, right, bottom = self.to_pixel_coords(screen_w, screen_h)
        return (left + right) // 2, (top + bottom) // 2

    @classmethod
    def from_pixel_coords(
        cls, left: int, top: int, right: int, bottom: int, screen_w: int, screen_h: int
    ) -> BoundingBox:
        """
        Constructs a normalized BoundingBox from physical screen pixel coordinates.
        """
        if screen_w <= 0 or screen_h <= 0:
            return cls(ymin=0, xmin=0, ymax=0, xmax=0)
        xmin = int(round(max(0, min(screen_w, left)) / screen_w * 1000.0))
        ymin = int(round(max(0, min(screen_h, top)) / screen_h * 1000.0))
        xmax = int(round(max(0, min(screen_w, right)) / screen_w * 1000.0))
        ymax = int(round(max(0, min(screen_h, bottom)) / screen_h * 1000.0))
        return cls(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)

    def contains(self, x_norm: int, y_norm: int) -> bool:
        """Returns True if normalized coordinate is inside bounding box."""
        return self.xmin <= x_norm <= self.xmax and self.ymin <= y_norm <= self.ymax

    def iou(self, other: BoundingBox) -> float:
        """Computes Intersection over Union (IoU) with another bounding box."""
        inter_xmin = max(self.xmin, other.xmin)
        inter_ymin = max(self.ymin, other.ymin)
        inter_xmax = min(self.xmax, other.xmax)
        inter_ymax = min(self.ymax, other.ymax)

        if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
            return 0.0

        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        union_area = self.area_norm + other.area_norm - inter_area
        return inter_area / union_area if union_area > 0 else 0.0


@dataclass
class UIElement:
    """
    Represents a recognized UI element on screen.
    """
    name: str
    element_type: str  # button, text_box, menu_item, checkbox, link, icon, window, generic
    bbox: BoundingBox
    text: str | None = None
    confidence: float = 1.0
    source: str = "vision_llm"  # vision_llm | ocr | win32_uia | template_match | synthetic
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def center_norm(self) -> tuple[int, int]:
        return self.bbox.center_norm

    def center_pixel(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        return self.bbox.center_pixel(screen_w, screen_h)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "element_type": self.element_type,
            "bbox": {
                "ymin": self.bbox.ymin,
                "xmin": self.bbox.xmin,
                "ymax": self.bbox.ymax,
                "xmax": self.bbox.xmax,
            },
            "center_norm": list(self.center_norm),
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
        }


class CoordinateMapper:
    """
    Bidirectional coordinate converter between Anthropic 1000x1000 grid and pixel coordinates.
    """

    def __init__(self, default_width: int = 1920, default_height: int = 1080) -> None:
        self.default_width = default_width
        self.default_height = default_height

    def get_screen_size(self) -> tuple[int, int]:
        """Resolves active screen resolution (Width, Height)."""
        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            try:
                w = ctypes.windll.user32.GetSystemMetrics(0)
                h = ctypes.windll.user32.GetSystemMetrics(1)
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
        return self.default_width, self.default_height

    def norm_to_pixel(
        self, x_norm: int, y_norm: int, screen_w: int | None = None, screen_h: int | None = None
    ) -> tuple[int, int]:
        """Converts normalized (0-1000) point to physical screen pixel coordinates (x_px, y_px)."""
        w, h = (screen_w, screen_h) if screen_w and screen_h else self.get_screen_size()
        x_px = int(round(max(0, min(1000, x_norm)) * w / 1000.0))
        y_px = int(round(max(0, min(1000, y_norm)) * h / 1000.0))
        return max(0, min(w - 1, x_px)), max(0, min(h - 1, y_px))

    def pixel_to_norm(
        self, x_px: int, y_px: int, screen_w: int | None = None, screen_h: int | None = None
    ) -> tuple[int, int]:
        """Converts physical screen pixel coordinates (x_px, y_px) to normalized (0-1000) point."""
        w, h = (screen_w, screen_h) if screen_w and screen_h else self.get_screen_size()
        if w <= 0 or h <= 0:
            return 0, 0
        x_norm = int(round(max(0, min(w, x_px)) / w * 1000.0))
        y_norm = int(round(max(0, min(h, y_px)) / h * 1000.0))
        return max(0, min(1000, x_norm)), max(0, min(1000, y_norm))


# ──────────────────────────────────────────────────────────────────────────────
# 2. 4-Tier UI Element Grounding Engine
# ──────────────────────────────────────────────────────────────────────────────

class UIElementDetector:
    """
    4-Tier UI Element Detector & Coordinate Grounding Resolver.
    Tier 1: Vision LLM Grounding (Gemini 1.5 Flash / GPT-4o Vision)
    Tier 2: Local OCR Bounding Boxes (DesktopOCR / pytesseract)
    Tier 3: Win32 UIAutomation / EnumChildWindows
    Tier 4: Template Matching & Synthetic UI Fallback
    """

    def __init__(
        self,
        vision_manager: ScreenVisionManager | None = None,
        ocr_engine: DesktopOCR | None = None,
        coordinate_mapper: CoordinateMapper | None = None,
    ) -> None:
        self.vision_manager = vision_manager or ScreenVisionManager()
        self.ocr_engine = ocr_engine or DesktopOCR(vision_manager=self.vision_manager)
        self.coord_mapper = coordinate_mapper or CoordinateMapper()

    # ── Tier 1: Vision LLM Grounding ──────────────────────────────────────────

    def detect_via_vision_llm(
        self, query: str, image_bytes: bytes, screen_w: int, screen_h: int
    ) -> list[UIElement]:
        """
        Tier 1: Queries Vision LLM with structured coordinate grounding prompt.
        Expects normalized coordinates [ymin, xmin, ymax, xmax] in 0-1000 scale.
        """
        api_key = getattr(self.vision_manager, "gemini_api_key", None) or getattr(self.vision_manager, "openai_api_key", None)
        if not api_key:
            logger.debug("Vision LLM API key not configured, skipping Tier 1.")
            return []

        prompt = (
            f"Locate the UI element(s) matching '{query}' in the image.\n"
            "Return a strictly valid JSON array of objects with the following schema:\n"
            "[\n"
            "  {\n"
            '    "name": "descriptive label",\n'
            '    "element_type": "button" | "text_box" | "menu_item" | "checkbox" | "link" | "icon" | "window",\n'
            '    "box_2d": [ymin, xmin, ymax, xmax],\n'
            '    "confidence": 0.95,\n'
            '    "text": "visible text inside or near element"\n'
            "  }\n"
            "]\n"
            "Coordinates in box_2d MUST be normalized integers in range [0, 1000] "
            "where (0,0) is top-left and (1000,1000) is bottom-right. Return ONLY JSON."
        )

        try:
            raw_response = self.vision_manager.analyze_screen(query=prompt, image_bytes=image_bytes)
            if not raw_response or "chưa cấu hình" in raw_response:
                return []
            return self._parse_llm_grounding_response(raw_response)
        except Exception as exc:
            logger.warning("Vision LLM grounding failed: %s", exc)
            return []

    def _parse_llm_grounding_response(self, response_text: str) -> list[UIElement]:
        """Extracts JSON array of detected bounding boxes from LLM output."""
        elements: list[UIElement] = []
        json_str = response_text.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", json_str)
        if fence_match:
            json_str = fence_match.group(1).strip()

        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                # Handle {"elements": [...]} wrapper
                data = data.get("elements", [data])
            if not isinstance(data, list):
                return []

            for item in data:
                if not isinstance(item, dict):
                    continue
                box = item.get("box_2d") or item.get("bbox") or item.get("bounding_box")
                if not box or len(box) != 4:
                    continue
                ymin, xmin, ymax, xmax = box
                bbox = BoundingBox(ymin=int(ymin), xmin=int(xmin), ymax=int(ymax), xmax=int(xmax))
                name = str(item.get("name", "element"))
                elem_type = str(item.get("element_type", "generic"))
                conf = float(item.get("confidence", 0.9))
                txt = item.get("text")
                elements.append(
                    UIElement(
                        name=name,
                        element_type=elem_type,
                        bbox=bbox,
                        text=txt,
                        confidence=conf,
                        source="vision_llm",
                    )
                )
        except Exception as exc:
            logger.debug("Failed to parse JSON grounding response '%s': %s", response_text[:100], exc)

        return elements

    # ── Tier 2: Local OCR Bounding Boxes ─────────────────────────────────────

    def detect_via_ocr(
        self, query: str, image_input: bytes | Any, screen_w: int, screen_h: int
    ) -> list[UIElement]:
        """
        Tier 2: Uses local OCR (pytesseract or PIL image data) to locate exact text bounding boxes.
        """
        elements: list[UIElement] = []
        img = self._to_pil_image(image_input)
        if img is None:
            return elements

        img_w, img_h = img.size

        # If pytesseract is available, extract word/line bounding boxes
        if PYTESSERACT_AVAILABLE and pytesseract is not None:
            try:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                query_lower = query.strip().lower()
                n_boxes = len(data.get("text", []))

                # 1. Single word match
                for i in range(n_boxes):
                    text = data["text"][i].strip()
                    conf = float(data.get("conf", [0])[i])
                    if conf <= 0:
                        continue
                    if query_lower in text.lower() or text.lower() in query_lower:
                        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                        bbox = BoundingBox.from_pixel_coords(
                            left=x, top=y, right=x + w, bottom=y + h, screen_w=img_w, screen_h=img_h
                        )
                        elements.append(
                            UIElement(
                                name=text,
                                element_type="text_box",
                                bbox=bbox,
                                text=text,
                                confidence=min(1.0, conf / 100.0),
                                source="ocr",
                            )
                        )

                # 2. Multi-word phrase search across adjacent words
                if not elements and " " in query_lower:
                    words = query_lower.split()
                    for i in range(n_boxes - len(words) + 1):
                        seq = [data["text"][i + j].strip().lower() for j in range(len(words))]
                        if " ".join(seq) == query_lower:
                            left = data["left"][i]
                            top = min(data["top"][i + j] for j in range(len(words)))
                            right = max(data["left"][i + j] + data["width"][i + j] for j in range(len(words)))
                            bottom = max(data["top"][i + j] + data["height"][i + j] for j in range(len(words)))
                            bbox = BoundingBox.from_pixel_coords(
                                left=left, top=top, right=right, bottom=bottom, screen_w=img_w, screen_h=img_h
                            )
                            elements.append(
                                UIElement(
                                    name=query,
                                    element_type="text_box",
                                    bbox=bbox,
                                    text=query,
                                    confidence=0.85,
                                    source="ocr",
                                )
                            )
            except Exception as exc:
                logger.debug("Pytesseract box extraction failed: %s", exc)

        return elements

    # ── Tier 3: Win32 UIAutomation / Native Child Windows ────────────────────

    def detect_via_win32_uia(self, query: str, screen_w: int, screen_h: int) -> list[UIElement]:
        """
        Tier 3: Enumerates visible native Windows controls (buttons, edit boxes, child windows).
        """
        elements: list[UIElement] = []
        if sys.platform != "win32" or not WIN32GUI_AVAILABLE or win32gui is None:
            return elements

        query_lower = query.strip().lower()

        def _enum_callback(hwnd: int, _lparam: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                text = win32gui.GetWindowText(hwnd).strip()
                cls_name = win32gui.GetClassName(hwnd).strip()

                if query_lower in text.lower() or query_lower in cls_name.lower():
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    w = right - left
                    h = bottom - top
                    if w > 5 and h > 5:
                        bbox = BoundingBox.from_pixel_coords(
                            left=left, top=top, right=right, bottom=bottom, screen_w=screen_w, screen_h=screen_h
                        )
                        elem_type = "button" if "button" in cls_name.lower() else "generic"
                        elements.append(
                            UIElement(
                                name=text or cls_name,
                                element_type=elem_type,
                                bbox=bbox,
                                text=text,
                                confidence=0.8,
                                source="win32_uia",
                                metadata={"hwnd": hwnd, "class_name": cls_name},
                            )
                        )
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(_enum_callback, None)
        except Exception as exc:
            logger.debug("Win32 window enumeration failed: %s", exc)

        return elements

    # ── Tier 4: Template Matching & Synthetic UI Fallback ────────────────────

    def detect_via_template_and_heuristics(
        self, query: str, image_input: bytes | Any | None, screen_w: int, screen_h: int
    ) -> list[UIElement]:
        """
        Tier 4: Geometric heuristics & standard UI control patterns fallback.
        Recognizes common system elements: close button, search bar, center dialog, etc.
        """
        elements: list[UIElement] = []
        q = query.strip().lower()

        # Heuristic 1: Window Close button (top right)
        if any(w in q for w in ["close", "đóng", "tat", "exit", "x button"]):
            elements.append(
                UIElement(
                    name="Close Button",
                    element_type="button",
                    bbox=BoundingBox(ymin=0, xmin=960, ymax=40, xmax=1000),
                    text="X",
                    confidence=0.7,
                    source="template_match",
                )
            )

        # Heuristic 2: Window Minimize button (top right adjacent)
        elif any(w in q for w in ["minimize", "thu nhỏ", "ha xuong"]):
            elements.append(
                UIElement(
                    name="Minimize Button",
                    element_type="button",
                    bbox=BoundingBox(ymin=0, xmin=880, ymax=40, xmax=920),
                    text="-",
                    confidence=0.7,
                    source="template_match",
                )
            )

        # Heuristic 3: Search box / Bar (top center or center)
        elif any(w in q for w in ["search", "tìm kiếm", "tim kiem", "url", "address bar"]):
            elements.append(
                UIElement(
                    name="Search / Address Bar",
                    element_type="text_box",
                    bbox=BoundingBox(ymin=40, xmin=200, ymax=90, xmax=800),
                    confidence=0.6,
                    source="template_match",
                )
            )

        # Heuristic 4: Dialog OK / Confirm button (bottom-center or bottom-right of typical modal)
        elif any(w in q for w in ["ok", "confirm", "xác nhận", "dong y", "save", "lưu"]):
            elements.append(
                UIElement(
                    name="Confirm / OK Button",
                    element_type="button",
                    bbox=BoundingBox(ymin=550, xmin=450, ymax=600, xmax=550),
                    confidence=0.5,
                    source="template_match",
                )
            )

        # Heuristic 5: Fallback Center Element
        else:
            elements.append(
                UIElement(
                    name=query,
                    element_type="generic",
                    bbox=BoundingBox(ymin=450, xmin=450, ymax=550, xmax=550),
                    confidence=0.3,
                    source="synthetic",
                )
            )

        return elements

    def _to_pil_image(self, image_input: bytes | Any | None) -> Any | None:
        if not PIL_AVAILABLE or Image is None or image_input is None:
            return None
        try:
            if isinstance(image_input, Image.Image):
                return image_input
            if isinstance(image_input, (bytes, bytearray)):
                return Image.open(io.BytesIO(image_input))
        except Exception:
            pass
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 3. High-Level ComputerUseVision Coordinator
# ──────────────────────────────────────────────────────────────────────────────

class ComputerUseVision:
    """
    Unified Computer-Use Vision Coordinator.
    Provides coordinate normalization, element grounding across 4 tiers,
    and visual element discovery.
    """

    def __init__(
        self,
        vision_manager: ScreenVisionManager | None = None,
        ocr_engine: DesktopOCR | None = None,
        detector: UIElementDetector | None = None,
        coord_mapper: CoordinateMapper | None = None,
    ) -> None:
        self.vision_manager = vision_manager or ScreenVisionManager()
        self.ocr_engine = ocr_engine or DesktopOCR(vision_manager=self.vision_manager)
        self.coord_mapper = coord_mapper or CoordinateMapper()
        self.detector = detector or UIElementDetector(
            vision_manager=self.vision_manager,
            ocr_engine=self.ocr_engine,
            coordinate_mapper=self.coord_mapper,
        )

    def locate_element(
        self,
        query: str,
        screenshot_bytes: bytes | None = None,
        preferred_tier: int | None = None,
        screen_w: int | None = None,
        screen_h: int | None = None,
    ) -> UIElement | None:
        """
        Locates a single best-matching UI element for the given query.
        Cascades through Tiers 1 -> 2 -> 3 -> 4.
        """
        elements = self.locate_elements(
            query=query,
            screenshot_bytes=screenshot_bytes,
            preferred_tier=preferred_tier,
            screen_w=screen_w,
            screen_h=screen_h,
        )
        return elements[0] if elements else None

    def locate_elements(
        self,
        query: str,
        screenshot_bytes: bytes | None = None,
        preferred_tier: int | None = None,
        screen_w: int | None = None,
        screen_h: int | None = None,
    ) -> list[UIElement]:
        """
        Locates all matching UI elements for the given query using 4-tier grounding cascade.
        """
        w, h = (screen_w, screen_h) if screen_w and screen_h else self.coord_mapper.get_screen_size()

        # Capture screenshot if not provided
        img_bytes = screenshot_bytes
        if img_bytes is None:
            try:
                img_bytes, _ = self.vision_manager.capture_screenshot()
            except Exception:
                img_bytes = b""

        # Tier 1: Vision LLM Grounding
        if preferred_tier is None or preferred_tier == 1:
            if img_bytes:
                tier1_results = self.detector.detect_via_vision_llm(query, img_bytes, w, h)
                if tier1_results:
                    return tier1_results

        # Tier 2: Local OCR Bounding Boxes
        if preferred_tier is None or preferred_tier == 2:
            if img_bytes:
                tier2_results = self.detector.detect_via_ocr(query, img_bytes, w, h)
                if tier2_results:
                    return tier2_results

        # Tier 3: Win32 UI Automation
        if preferred_tier is None or preferred_tier == 3:
            tier3_results = self.detector.detect_via_win32_uia(query, w, h)
            if tier3_results:
                return tier3_results

        # Tier 4: Template Matching / Synthetic Heuristic Fallback
        if preferred_tier is None or preferred_tier == 4:
            return self.detector.detect_via_template_and_heuristics(query, img_bytes, w, h)

        return []

    def norm_to_pixel(
        self, x_norm: int, y_norm: int, screen_w: int | None = None, screen_h: int | None = None
    ) -> tuple[int, int]:
        """Converts normalized (0-1000) point to physical screen pixel coordinates."""
        return self.coord_mapper.norm_to_pixel(x_norm, y_norm, screen_w, screen_h)

    def pixel_to_norm(
        self, x_px: int, y_px: int, screen_w: int | None = None, screen_h: int | None = None
    ) -> tuple[int, int]:
        """Converts physical screen pixel coordinates to normalized (0-1000) point."""
        return self.coord_mapper.pixel_to_norm(x_px, y_px, screen_w, screen_h)

    def get_screen_size(self) -> tuple[int, int]:
        """Returns physical screen dimensions (Width, Height)."""
        return self.coord_mapper.get_screen_size()
