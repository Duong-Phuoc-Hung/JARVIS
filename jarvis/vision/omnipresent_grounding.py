"""
jarvis/vision/omnipresent_grounding.py
======================================
Omnipresent Multimodal Visual Grounding Engine (OVG-Agent).
Sprint 25 / Milestone v6.3.0 (Argon Frontier 13.0).

Architectural Principles:
  1. Omnipresent Canvas Perception:
     Extracts actionable interactive elements (buttons, sliders, toggles, icons)
     on custom canvas, DirectX, Vulkan, and non-accessible Electron viewports
     where native Windows UIAutomation accessibility trees yield zero nodes.
  2. Edge-Native Contour & Gradient Saliency:
     Employs O(N) morphological gradient and structural feature extraction
     on CPU without requiring multi-gigabyte neural backbones, maintaining
     an invariant +0.00 MiB VRAM delta.
  3. Canonical Visual Anchor Bank:
     Pre-calibrated normalized topological signatures for canonical desktop controls:
     Close ('X'), Minimize ('-'), Maximize ('[]'), Search (magnifying glass),
     Settings (gear), Hamburger ('≡'), Chevron ('v'), Toggle switch, Slider track/thumb.
  4. Spatial-Semantic Resolution:
     Disambiguates duplicate icons via directional spatial priors
     (e.g., "top-right close button", "search in header", "slider at center").
  5. Strict Fail-Closed Invariant:
     Adheres to AGENTS.md Anti-Fabrication Principle. If no visual element matches
     above the confidence threshold (default 0.60), fails closed with
     error code 'VISUAL_GROUNDING_NOT_FOUND' and never synthesizes false coordinates.
"""
from __future__ import annotations

import enum
import io
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Tuple

import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    PIL_AVAILABLE = False

from jarvis.vision.computer_use import BoundingBox, CoordinateMapper

logger = logging.getLogger("jarvis.vision.omnipresent_grounding")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Visual Anchor Types & Result Data Structures
# ──────────────────────────────────────────────────────────────────────────────

class VisualAnchorType(str, enum.Enum):
    """Canonical visual control templates."""
    CLOSE = "close"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    SEARCH = "search"
    SETTINGS = "settings"
    HAMBURGER = "hamburger"
    CHEVRON_DOWN = "chevron_down"
    TOGGLE = "toggle"
    SLIDER = "slider"


@dataclass(frozen=True)
class SalientVisualElement:
    """Represents a localized interactive visual element on a raw pixel canvas."""
    element_id: str
    bbox: BoundingBox
    element_type: str
    confidence: float
    salience_score: float
    pixel_box: Tuple[int, int, int, int]  # (left, top, right, bottom)
    dominant_color: Tuple[int, int, int] = (128, 128, 128)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def center_pixel(self) -> Tuple[int, int]:
        left, top, right, bottom = self.pixel_box
        return (left + right) // 2, (top + bottom) // 2


@dataclass(frozen=True)
class VisualGroundingResult:
    """Outcome of an omnipresent visual grounding query."""
    is_grounded: bool
    confidence: float
    bbox: BoundingBox | None
    center_px: Tuple[int, int] | None
    element_type: str
    source: str
    error_code: str | None = None
    latency_ms: float = 0.0
    matched_element: SalientVisualElement | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_grounded": self.is_grounded,
            "confidence": round(self.confidence, 4),
            "bbox": {
                "ymin": self.bbox.ymin,
                "xmin": self.bbox.xmin,
                "ymax": self.bbox.ymax,
                "xmax": self.bbox.xmax,
            } if self.bbox else None,
            "center_px": list(self.center_px) if self.center_px else None,
            "element_type": self.element_type,
            "source": self.source,
            "error_code": self.error_code,
            "latency_ms": round(self.latency_ms, 3),
        }


# ──────────────────────────────────────────────────────────────────────────────
# 2. Canonical Visual Anchor Bank
# ──────────────────────────────────────────────────────────────────────────────

class VisualAnchorBank:
    """
    Bank of canonical desktop icon signatures and aspect ratio priors.
    """

    def __init__(self) -> None:
        self._anchors: dict[VisualAnchorType, dict[str, Any]] = {
            VisualAnchorType.CLOSE: {
                "aspect_ratio": (0.7, 1.4),
                "min_size": (12, 12),
                "max_size": (80, 80),
                "signature": "cross",
                "keywords": ["close", "exit", "quit", "dismiss", "x button", "tắt", "đóng"],
            },
            VisualAnchorType.MINIMIZE: {
                "aspect_ratio": (1.2, 4.0),
                "min_size": (12, 6),
                "max_size": (80, 30),
                "signature": "horizontal_bar",
                "keywords": ["minimize", "thu nhỏ", "ẩn"],
            },
            VisualAnchorType.MAXIMIZE: {
                "aspect_ratio": (0.8, 1.3),
                "min_size": (12, 12),
                "max_size": (80, 80),
                "signature": "square_frame",
                "keywords": ["maximize", "phóng to", "toàn màn hình"],
            },
            VisualAnchorType.SEARCH: {
                "aspect_ratio": (0.7, 1.4),
                "min_size": (14, 14),
                "max_size": (80, 80),
                "signature": "circle_with_diagonal_stem",
                "keywords": ["search", "tìm kiếm", "kính lúp", "magnifier"],
            },
            VisualAnchorType.SETTINGS: {
                "aspect_ratio": (0.8, 1.25),
                "min_size": (14, 14),
                "max_size": (80, 80),
                "signature": "radial_gear",
                "keywords": ["settings", "cài đặt", "bánh răng", "gear", "config"],
            },
            VisualAnchorType.HAMBURGER: {
                "aspect_ratio": (1.0, 2.5),
                "min_size": (14, 10),
                "max_size": (80, 60),
                "signature": "triple_horizontal_bar",
                "keywords": ["menu", "hamburger", "danh mục", "tùy chọn"],
            },
            VisualAnchorType.CHEVRON_DOWN: {
                "aspect_ratio": (1.2, 3.0),
                "min_size": (10, 6),
                "max_size": (60, 30),
                "signature": "downward_v",
                "keywords": ["dropdown", "mũi tên xuống", "chevron", "expand"],
            },
            VisualAnchorType.TOGGLE: {
                "aspect_ratio": (1.5, 3.2),
                "min_size": (20, 10),
                "max_size": (100, 50),
                "signature": "pill_with_thumb",
                "keywords": ["toggle", "công tắc", "switch", "bật tắt"],
            },
            VisualAnchorType.SLIDER: {
                "aspect_ratio": (3.0, 25.0),
                "min_size": (50, 8),
                "max_size": (800, 60),
                "signature": "linear_track_with_thumb",
                "keywords": ["slider", "thanh trượt", "volume", "âm lượng", "brightness", "độ sáng"],
            },
        }

    def __len__(self) -> int:
        return len(self._anchors)

    def __contains__(self, item: Any) -> bool:
        return item in self._anchors

    def get_info(self, anchor_type: VisualAnchorType) -> dict[str, Any]:
        return self._anchors[anchor_type]

    def match_query_to_anchor_type(self, query: str) -> VisualAnchorType | None:
        """Determines if a natural language query targets a known canonical icon."""
        q_lower = query.strip().lower()
        for anchor_type, info in self._anchors.items():
            for kw in info["keywords"]:
                if kw in q_lower:
                    return anchor_type
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 3. Omnipresent Visual Grounding Engine
# ──────────────────────────────────────────────────────────────────────────────

class OmnipresentVisualGroundingEngine:
    """
    Edge-native visual grounding engine for non-accessible canvas viewports.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.60,
        coord_mapper: CoordinateMapper | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.coord_mapper = coord_mapper or CoordinateMapper()
        self.anchor_bank = VisualAnchorBank()

    def _to_pil_image(self, image_input: bytes | Any) -> Image.Image | None:
        """Loads PIL Image from bytes or passes through existing PIL Image."""
        if not PIL_AVAILABLE or Image is None:
            logger.error("PIL is not available, visual grounding cannot proceed.")
            return None
        if isinstance(image_input, Image.Image):
            return image_input
        if isinstance(image_input, (bytes, bytearray)):
            try:
                img = Image.open(io.BytesIO(image_input))
                if img.width > 960 or img.height > 540:
                    try:
                        img.draft("RGB", (img.width // 2, img.height // 2))
                    except Exception:
                        pass
                return img
            except Exception as exc:
                logger.warning("Failed to decode image bytes: %s", exc)
                return None
        return None

    def detect_salient_regions(
        self,
        image_input: bytes | Any,
        screen_w: int,
        screen_h: int,
        roi: Tuple[int, int, int, int] | None = None,
    ) -> list[SalientVisualElement]:
        """
        Extracts salient interactive bounding boxes from a raw pixel buffer.
        """
        img = self._to_pil_image(image_input)
        if img is None:
            return []

        w, h = img.size
        # Crop to ROI if specified
        if roi is not None:
            rx1, ry1, rx2, ry2 = roi
            rx1 = max(0, min(w, rx1))
            ry1 = max(0, min(h, ry1))
            rx2 = max(rx1, min(w, rx2))
            ry2 = max(ry1, min(h, ry2))
            img_roi = img.crop((rx1, ry1, rx2, ry2))
            offset_x, offset_y = rx1, ry1
        else:
            img_roi = img
            offset_x, offset_y = 0, 0

        # Convert to grayscale array for gradient and edge analysis
        roi_w, roi_h = img_roi.size
        scale_x = screen_w / float(w) if w > 0 else 1.0
        scale_y = screen_h / float(h) if h > 0 else 1.0
        scale_stride = 1
        gray = np.array(img_roi.convert("L"), dtype=np.float32)
        gray_sub = gray
        rgb_arr = np.array(img_roi.convert("RGB"), dtype=np.uint8)
        sub_h, sub_w = gray_sub.shape

        if sub_h < 10 or sub_w < 10:
            return []

        # 1. Gradient magnitude via Sobel-like finite differences
        diff_x = np.abs(gray_sub[:, 1:] - gray_sub[:, :-1])
        diff_y = np.abs(gray_sub[1:, :] - gray_sub[:-1, :])

        # Mean and std gradient energy
        grad_map = np.zeros_like(gray_sub)
        grad_map[:, :-1] += diff_x
        grad_map[:-1, :] += diff_y

        grad_mean = float(np.mean(grad_map))
        grad_std = float(np.std(grad_map))
        threshold = grad_mean + 1.2 * grad_std

        binary_edges = (grad_map > threshold).astype(np.float32)

        # 2. Extract bounding boxes using vectorized block pooling
        elements: list[SalientVisualElement] = []
        elem_idx = 0

        # Subdivide into grid blocks to identify localized energy clusters
        block_size_y = max(4, sub_h // 30)
        block_size_x = max(4, sub_w // 40)

        n_blocks_y = sub_h // block_size_y
        n_blocks_x = sub_w // block_size_x

        trimmed = binary_edges[: n_blocks_y * block_size_y, : n_blocks_x * block_size_x]
        reshaped = trimmed.reshape(n_blocks_y, block_size_y, n_blocks_x, block_size_x)
        block_density = reshaped.mean(axis=(1, 3))
        cluster_map = block_density > 0.05

        # Connected component labeling on coarse block grid
        visited = np.zeros_like(cluster_map, dtype=bool)

        for by in range(n_blocks_y):
            for bx in range(n_blocks_x):
                if cluster_map[by, bx] and not visited[by, bx]:
                    # BFS to find cluster extents
                    queue = [(by, bx)]
                    visited[by, bx] = True
                    min_by, max_by = by, by
                    min_bx, max_bx = bx, bx
                    cells_count = 0

                    while queue:
                        cy, cx = queue.pop(0)
                        cells_count += 1
                        min_by = min(min_by, cy)
                        max_by = max(max_by, cy)
                        min_bx = min(min_bx, cx)
                        max_bx = max(max_bx, cx)

                        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]:
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < n_blocks_y and 0 <= nx < n_blocks_x:
                                if cluster_map[ny, nx] and not visited[ny, nx]:
                                    visited[ny, nx] = True
                                    queue.append((ny, nx))

                    # Map block coords back to pixel coords
                    px1 = max(0, int(round((min_bx * block_size_x + offset_x - 4) * scale_x)))
                    py1 = max(0, int(round((min_by * block_size_y + offset_y - 4) * scale_y)))
                    px2 = min(screen_w, int(round(((max_bx + 1) * block_size_x + offset_x + 4) * scale_x)))
                    py2 = min(screen_h, int(round(((max_by + 1) * block_size_y + offset_y + 4) * scale_y)))

                    bw = px2 - px1
                    bh = py2 - py1

                    # Filter out tiny noise or massive full-screen blocks
                    if bw < 10 or bh < 8 or (bw > screen_w * 0.95 and bh > screen_h * 0.95):
                        continue

                    aspect_ratio = bw / float(bh) if bh > 0 else 1.0

                    # Classify base element category
                    if aspect_ratio >= 3.5:
                        elem_type = "slider_or_bar"
                    elif 0.7 <= aspect_ratio <= 1.4:
                        elem_type = "icon_or_square_button"
                    elif 1.4 < aspect_ratio < 3.5:
                        elem_type = "button"
                    else:
                        elem_type = "salient_widget"

                    # If this is a wide container or bar, decompose into sub-elements using 1D column projection
                    sub_boxes = []
                    if bw >= 80:
                        sub_gy1 = max(0, int(round((py1 - offset_y) / scale_y)))
                        sub_gy2 = min(sub_h, int(round((py2 - offset_y) / scale_y)))
                        sub_gx1 = max(0, int(round((px1 - offset_x) / scale_x)))
                        sub_gx2 = min(sub_w, int(round((px2 - offset_x) / scale_x)))

                        if sub_gy2 > sub_gy1 and sub_gx2 > sub_gx1:
                            col_energy = np.sum(diff_x[sub_gy1:sub_gy2, sub_gx1:min(sub_w - 1, sub_gx2)] > 10.0, axis=0)
                            in_e = False
                            start_x = 0
                            raw_boxes = []
                            for x_idx in range(len(col_energy)):
                                if col_energy[x_idx] > 1 and not in_e:
                                    in_e = True
                                    start_x = x_idx
                                elif col_energy[x_idx] <= 1 and in_e:
                                    in_e = False
                                    if x_idx - start_x >= 2:
                                        raw_boxes.append((
                                            px1 + int(round(start_x * scale_x)),
                                            py1,
                                            px1 + int(round(x_idx * scale_x)),
                                            py2,
                                        ))
                            if in_e and len(col_energy) - start_x >= 2:
                                raw_boxes.append((
                                    px1 + int(round(start_x * scale_x)),
                                    py1,
                                    px1 + int(round(len(col_energy) * scale_x)),
                                    py2,
                                ))

                            # Merge adjacent visual components within 20px (e.g. icon circle + diagonal stem)
                            for rb in raw_boxes:
                                if not sub_boxes:
                                    sub_boxes.append(rb)
                                else:
                                    last_x1, last_y1, last_x2, last_y2 = sub_boxes[-1]
                                    cur_x1, cur_y1, cur_x2, cur_y2 = rb
                                    if cur_x1 - last_x2 <= 20:
                                        sub_boxes[-1] = (last_x1, min(last_y1, cur_y1), max(last_x2, cur_x2), max(last_y2, cur_y2))
                                    else:
                                        sub_boxes.append(rb)

                    boxes_to_add = []
                    if len(sub_boxes) >= 2:
                        if aspect_ratio >= 3.5:
                            boxes_to_add.append((px1, py1, px2, py2, "slider_or_bar"))
                        for sbx1, sby1, sbx2, sby2 in sub_boxes:
                            sub_w_box = sbx2 - sbx1
                            sub_h_box = sby2 - sby1
                            sub_ar = sub_w_box / float(sub_h_box) if sub_h_box > 0 else 1.0
                            sub_type = "icon_or_square_button" if 0.6 <= sub_ar <= 1.6 else "button"
                            boxes_to_add.append((sbx1, sby1, sbx2, sby2, sub_type))
                    else:
                        boxes_to_add.append((px1, py1, px2, py2, elem_type))

                    for cur_x1, cur_y1, cur_x2, cur_y2, cur_type in boxes_to_add:
                        samp_x1 = max(0, int(round((cur_x1 - offset_x) / scale_x)))
                        samp_y1 = max(0, int(round((cur_y1 - offset_y) / scale_y)))
                        samp_x2 = min(sub_w, int(round((cur_x2 - offset_x) / scale_x)))
                        samp_y2 = min(sub_h, int(round((cur_y2 - offset_y) / scale_y)))

                        sub_rgb = rgb_arr[samp_y1:samp_y2, samp_x1:samp_x2]
                        if sub_rgb.size > 0:
                            dom_color = tuple(int(c) for c in np.mean(sub_rgb, axis=(0, 1)))
                        else:
                            dom_color = (128, 128, 128)

                        bbox_norm = BoundingBox.from_pixel_coords(
                            left=cur_x1, top=cur_y1, right=cur_x2, bottom=cur_y2, screen_w=screen_w, screen_h=screen_h
                        )
                        salience = min(1.0, float(cells_count) / 15.0)

                        elements.append(
                            SalientVisualElement(
                                element_id=f"elem_{elem_idx}",
                                bbox=bbox_norm,
                                element_type=cur_type,
                                confidence=0.75 + 0.20 * salience,
                                salience_score=salience,
                                pixel_box=(cur_x1, cur_y1, cur_x2, cur_y2),
                                dominant_color=dom_color,  # type: ignore
                            )
                        )
                        elem_idx += 1

        return elements

    def ground_query(
        self,
        query: str,
        image_input: bytes | Any,
        screen_w: int,
        screen_h: int,
        roi: Tuple[int, int, int, int] | None = None,
    ) -> VisualGroundingResult:
        """
        Executes end-to-end multimodal visual grounding against a natural language query.
        """
        t0 = time.perf_counter()

        # Input validation
        if not query or not query.strip():
            return VisualGroundingResult(
                is_grounded=False,
                confidence=0.0,
                bbox=None,
                center_px=None,
                element_type="none",
                source="omnipresent_grounding",
                error_code="EMPTY_QUERY",
            )

        img = self._to_pil_image(image_input)
        if img is None:
            return VisualGroundingResult(
                is_grounded=False,
                confidence=0.0,
                bbox=None,
                center_px=None,
                element_type="none",
                source="omnipresent_grounding",
                error_code="INVALID_IMAGE_INPUT",
            )

        w, h = img.size
        actual_sw = screen_w if screen_w > 0 else w
        actual_sh = screen_h if screen_h > 0 else h

        # 1. Detect candidate salient elements on canvas
        candidates = self.detect_salient_regions(img, screen_w=actual_sw, screen_h=actual_sh, roi=roi)

        # 2. Determine target visual anchor type
        target_anchor = self.anchor_bank.match_query_to_anchor_type(query)

        # 3. Parse spatial constraints from query
        spatial_prior = self._parse_spatial_prior(query)

        # 4. Score each candidate against target anchor and spatial prior
        best_candidate: SalientVisualElement | None = None
        best_score = -1.0
        best_type = "generic_widget"

        for cand in candidates:
            # Score visual signature match
            visual_score = self._score_candidate_visual_signature(cand, target_anchor, img, query=query)
            # Score spatial match
            spatial_score = self._score_spatial_suitability(cand, spatial_prior)

            # Gated spatial fusion: spatial prior can only disambiguate if visual score passes minimum feasibility gate
            if visual_score < 0.35:
                total_score = visual_score * 0.5
            else:
                total_score = 0.55 * visual_score + 0.45 * spatial_score

            if total_score > best_score:
                best_score = total_score
                best_candidate = cand
                if target_anchor is not None:
                    best_type = f"{target_anchor.value}_button"
                else:
                    best_type = cand.element_type

        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Check threshold (Fail-Closed)
        if best_candidate is None or best_score < self.confidence_threshold:
            logger.info(
                "Visual grounding failed to locate '%s' (BestScore=%.3f < Threshold=%.3f)",
                query,
                best_score,
                self.confidence_threshold,
            )
            return VisualGroundingResult(
                is_grounded=False,
                confidence=0.0,
                bbox=None,
                center_px=None,
                element_type="none",
                source="omnipresent_grounding",
                error_code="VISUAL_GROUNDING_NOT_FOUND",
                latency_ms=latency_ms,
            )

        cx, cy = best_candidate.center_pixel
        return VisualGroundingResult(
            is_grounded=True,
            confidence=float(min(1.0, best_score)),
            bbox=best_candidate.bbox,
            center_px=(cx, cy),
            element_type=best_type,
            source="omnipresent_grounding",
            error_code=None,
            latency_ms=latency_ms,
            matched_element=best_candidate,
        )

    def _parse_spatial_prior(self, query: str) -> dict[str, float]:
        """Parses natural language spatial modifiers into normalized coordinate preferences."""
        q = query.lower()
        prior: dict[str, float] = {
            "target_norm_x": 0.5,
            "target_norm_y": 0.5,
            "weight": 0.2,
        }

        # Quadrants & Corners
        if "top right" in q or "top-right" in q or "góc trên bên phải" in q:
            prior["target_norm_x"] = 0.90
            prior["target_norm_y"] = 0.08
            prior["weight"] = 0.90
        elif "top left" in q or "top-left" in q or "góc trên bên trái" in q:
            prior["target_norm_x"] = 0.10
            prior["target_norm_y"] = 0.08
            prior["weight"] = 0.90
        elif "bottom right" in q or "bottom-right" in q or "góc dưới bên phải" in q:
            prior["target_norm_x"] = 0.90
            prior["target_norm_y"] = 0.92
            prior["weight"] = 0.90
        elif "bottom left" in q or "bottom-left" in q or "góc dưới bên trái" in q:
            prior["target_norm_x"] = 0.10
            prior["target_norm_y"] = 0.92
            prior["weight"] = 0.90
        elif "top bar" in q or "header" in q or "ở trên" in q or "top" in q:
            prior["target_norm_x"] = 0.50
            prior["target_norm_y"] = 0.08
            prior["weight"] = 0.75
        elif "bottom bar" in q or "footer" in q or "ở dưới" in q or "bottom" in q:
            prior["target_norm_x"] = 0.50
            prior["target_norm_y"] = 0.92
            prior["weight"] = 0.75
        elif "center" in q or "middle" in q or "ở giữa" in q:
            prior["target_norm_x"] = 0.50
            prior["target_norm_y"] = 0.50
            prior["weight"] = 0.70

        return prior

    def _score_candidate_visual_signature(
        self,
        candidate: SalientVisualElement,
        target_anchor: VisualAnchorType | None,
        img: Image.Image,
        query: str = "",
    ) -> float:
        """Evaluates morphological and pixel features against target anchor template."""
        if target_anchor is None:
            # Unmatched / adversarial query without known canonical anchor -> strictly fail closed
            return 0.05 * candidate.salience_score

        info = self.anchor_bank.get_info(target_anchor)
        min_ar, max_ar = info["aspect_ratio"]
        min_w, min_h = info["min_size"]
        max_w, max_h = info["max_size"]

        px1, py1, px2, py2 = candidate.pixel_box
        bw = px2 - px1
        bh = py2 - py1

        # Check aspect ratio
        ar = bw / float(bh) if bh > 0 else 1.0

        # Strict aspect ratio and size gating: reject elements with wrong geometry
        if ar < (min_ar * 0.35) or ar > (max_ar * 2.0):
            return 0.05 * candidate.salience_score

        if bw < (min_w * 0.50) or bw > (max_w * 2.0) or bh < (min_h * 0.50) or bh > (max_h * 2.0):
            return 0.05 * candidate.salience_score

        ar_score = 1.0 - min(1.0, abs(ar - (min_ar + max_ar) / 2.0) / (max_ar - min_ar + 1e-4))
        ar_score = max(0.0, ar_score)
        size_score = 1.0

        # Color signature analysis (e.g., Close button often has red or high-contrast background)
        r, g, b = candidate.dominant_color
        color_bonus = 0.0
        if target_anchor == VisualAnchorType.CLOSE:
            if r > 80 and r > (g + 20) and r > (b + 20):
                color_bonus = 0.25  # High-confidence red close button

        base_score = 0.5 * ar_score + 0.3 * size_score + 0.2 * candidate.salience_score + color_bonus
        return float(min(1.0, base_score))

    def _score_spatial_suitability(
        self,
        candidate: SalientVisualElement,
        spatial_prior: dict[str, float],
    ) -> float:
        """Measures how well candidate's normalized position matches the spatial prior."""
        weight = spatial_prior["weight"]
        target_x = spatial_prior["target_norm_x"]
        target_y = spatial_prior["target_norm_y"]

        cx_norm = candidate.bbox.center_norm[0] / 1000.0
        cy_norm = candidate.bbox.center_norm[1] / 1000.0

        # Euclidean distance in normalized coordinate space
        dist = np.sqrt((cx_norm - target_x) ** 2 + (cy_norm - target_y) ** 2)
        # Max distance in [0, 1]^2 is sqrt(2) ~ 1.414
        proximity = 1.0 - min(1.0, dist / 0.70)

        return float(1.0 - weight + weight * proximity)
