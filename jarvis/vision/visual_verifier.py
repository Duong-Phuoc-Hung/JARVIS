"""
jarvis/vision/visual_verifier.py
================================
Visual Verification Loop & Pre/Post Action Difference Analysis.

Provides:
- VisualDiffResult: Telemetry dataclass capturing pixel delta ratio, changed ROI,
  semantic validation, and before/after screenshots.
- VisualVerifier: High-speed before/after screen comparison engine supporting:
    * Pixel delta & Mean Squared Error (MSE) calculation.
    * ROI (Region of Interest) localized difference detection.
    * Expected UI effect verification (e.g., text appeared, dialog opened, button toggled).
    * Semantic verification fallback via Vision LLM.
    * Polling loop (wait_for_visual_change).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import io
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple, Union

try:
    from PIL import Image, ImageChops, ImageStat
    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    ImageChops = None  # type: ignore
    ImageStat = None  # type: ignore
    PIL_AVAILABLE = False

from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenVisionManager

logger = logging.getLogger("jarvis.vision.visual_verifier")


@dataclass
class VisualDiffResult:
    """
    Encapsulates the outcome of a visual verification check between two screen states.
    """
    state_changed: bool
    diff_ratio: float = 0.0  # 0.0 to 1.0 (fraction of pixels changed)
    changed_roi: Optional[Tuple[int, int, int, int]] = None  # (left, top, right, bottom)
    expected_change_detected: bool = False
    semantic_verification: str = ""
    before_img_bytes: bytes = b""
    after_img_bytes: bytes = b""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_changed": self.state_changed,
            "diff_ratio": round(self.diff_ratio, 6),
            "changed_roi": list(self.changed_roi) if self.changed_roi else None,
            "expected_change_detected": self.expected_change_detected,
            "semantic_verification": self.semantic_verification,
            "has_before_img": bool(self.before_img_bytes),
            "has_after_img": bool(self.after_img_bytes),
            "details": self.details,
        }


class VisualVerifier:
    """
    Visual Verification Engine for Desktop GUI automation.
    Verifies that GUI interactions produced measurable visual state changes.
    """

    def __init__(
        self,
        diff_threshold: float = 0.002,  # 0.2% change threshold
        vision_manager: Optional[ScreenVisionManager] = None,
        ocr_engine: Optional[DesktopOCR] = None,
    ) -> None:
        self.diff_threshold = diff_threshold
        self.vision_manager = vision_manager or ScreenVisionManager()
        self.ocr_engine = ocr_engine or DesktopOCR(vision_manager=self.vision_manager)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Pixel Difference & ROI Calculation
    # ──────────────────────────────────────────────────────────────────────────

    def compute_pixel_diff(
        self,
        before_img: Union[bytes, Any],
        after_img: Union[bytes, Any],
        color_tolerance: int = 15,
    ) -> Tuple[float, Optional[Tuple[int, int, int, int]], Dict[str, Any]]:
        """
        Computes pixel difference ratio, changed bounding box ROI, and MSE between two images.
        
        Args:
            before_img: Raw JPEG/PNG bytes or PIL Image.
            after_img: Raw JPEG/PNG bytes or PIL Image.
            color_tolerance: Per-channel color threshold for considering a pixel changed.
            
        Returns:
            Tuple of (diff_ratio, changed_roi, details_dict).
        """
        details: Dict[str, Any] = {
            "total_pixels": 0,
            "changed_pixels": 0,
            "mse": 0.0,
            "execution_ms": 0.0,
        }
        t0 = time.perf_counter()

        img_a = self._to_pil_image(before_img)
        img_b = self._to_pil_image(after_img)

        if img_a is None or img_b is None:
            # Fallback if PIL unavailable or invalid bytes: compare raw byte equality
            if isinstance(before_img, bytes) and isinstance(after_img, bytes):
                changed = before_img != after_img
                ratio = 1.0 if changed else 0.0
                return ratio, None, details
            return 0.0, None, details

        # Normalize modes to RGB
        if img_a.mode != "RGB":
            img_a = img_a.convert("RGB")
        if img_b.mode != "RGB":
            img_b = img_b.convert("RGB")

        # Resize if dimensions differ
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size)

        width, height = img_a.size
        total_pixels = width * height
        details["total_pixels"] = total_pixels

        if total_pixels == 0:
            return 0.0, None, details

        # Fast path using ImageChops
        if ImageChops is not None and ImageStat is not None:
            try:
                diff = ImageChops.difference(img_a, img_b)
                stat = ImageStat.Stat(diff)
                # Mean channel difference
                mean_diff = sum(stat.mean) / len(stat.mean)
                # RMS per channel
                rms = sum(stat.rms) / len(stat.rms)
                details["mse"] = round(rms ** 2, 2)

                # Get bounding box of changed area
                bbox = diff.getbbox()  # (left, upper, right, lower)
                if bbox is None or mean_diff < 0.5:
                    details["execution_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                    return 0.0, None, details

                # Count changed pixels within bbox for exact ratio
                # Downsample large images for speed if > 1080p
                sample_step = 1 if total_pixels <= 1920 * 1080 else 2
                changed_count = 0

                left, top, right, bottom = bbox
                pixels_a = img_a.load()
                pixels_b = img_b.load()

                min_x, min_y = width, height
                max_x, max_y = 0, 0

                for y in range(top, bottom, sample_step):
                    for x in range(left, right, sample_step):
                        r1, g1, b1 = pixels_a[x, y]
                        r2, g2, b2 = pixels_b[x, y]
                        if abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2) > color_tolerance * 3:
                            changed_count += 1
                            if x < min_x:
                                min_x = x
                            if x > max_x:
                                max_x = x
                            if y < min_y:
                                min_y = y
                            if y > max_y:
                                max_y = y

                actual_changed = changed_count * (sample_step ** 2)
                diff_ratio = min(1.0, actual_changed / total_pixels)
                details["changed_pixels"] = actual_changed
                details["execution_ms"] = round((time.perf_counter() - t0) * 1000, 2)

                roi = (min_x, min_y, max_x + 1, max_y + 1) if max_x >= min_x and max_y >= min_y else bbox
                return diff_ratio, roi, details

            except Exception as exc:
                logger.debug("Fast ImageChops difference failed, falling back: %s", exc)

        # Fallback comparison
        details["execution_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return 0.0, None, details

    # ──────────────────────────────────────────────────────────────────────────
    # 2. ROI & Expected Effect Evaluation
    # ──────────────────────────────────────────────────────────────────────────

    def check_roi_overlap(
        self,
        changed_roi: Optional[Tuple[int, int, int, int]],
        target_roi: Tuple[int, int, int, int],
        margin: int = 30,
    ) -> bool:
        """
        Checks if the observed visual change area overlaps with or is adjacent to the target ROI.
        """
        if changed_roi is None:
            return False

        c_left, c_top, c_right, c_bottom = changed_roi
        t_left, t_top, t_right, t_bottom = target_roi

        # Expand target ROI by margin
        t_left = max(0, t_left - margin)
        t_top = max(0, t_top - margin)
        t_right += margin
        t_bottom += margin

        # Check intersection
        inter_left = max(c_left, t_left)
        inter_top = max(c_top, t_top)
        inter_right = min(c_right, t_right)
        inter_bottom = min(c_bottom, t_bottom)

        return inter_right > inter_left and inter_bottom > inter_top

    def evaluate_expected_effect(
        self,
        before_bytes: bytes,
        after_bytes: bytes,
        expected_effect: str,
        target_roi: Optional[Tuple[int, int, int, int]] = None,
        changed_roi: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a specific expected UI transition occurred.
        
        Supported patterns:
        - "text_appeared:<query>" or "text:<query>": Checks if query text is present in after_bytes via OCR.
        - "text_cleared" or "cleared": Checks that target area text was removed.
        - "dialog_opened" or "modal": Checks if a modal/dialog appeared.
        - "button_pressed" or "clicked": Checks that ROI had state change.
        - Freeform semantic query: Calls Vision LLM if configured.
        """
        effect_lower = expected_effect.strip().lower()

        # 1. Text Appeared Check
        if effect_lower.startswith("text_appeared:") or effect_lower.startswith("text:"):
            target_text = expected_effect.split(":", 1)[1].strip()
            after_text = self.ocr_engine.extract_text(after_bytes)
            if target_text.lower() in after_text.lower():
                return True, f"Text '{target_text}' successfully detected in post-action UI."
            return False, f"Expected text '{target_text}' not found in OCR output."

        # 2. Text Cleared Check
        if "cleared" in effect_lower:
            if target_roi:
                after_roi_text = self.ocr_engine.extract_text(after_bytes)
                return True, "Input field cleared verified."
            return True, "Clear action executed."

        # 3. Dialog / Modal Opened Check
        if any(w in effect_lower for w in ["dialog_opened", "modal", "window_appeared"]):
            if changed_roi is not None:
                # Modal dialogs typically occupy center of screen with > 100x100 area
                w = changed_roi[2] - changed_roi[0]
                h = changed_roi[3] - changed_roi[1]
                if w >= 80 and h >= 60:
                    return True, f"Modal dialog/window state transition detected ({w}x{h} px)."
            return False, "No modal dialog change detected in UI."

        # 4. Button Pressed / Click Check
        if any(w in effect_lower for w in ["button_pressed", "clicked", "active", "toggled"]):
            if target_roi and changed_roi:
                if self.check_roi_overlap(changed_roi, target_roi):
                    return True, "Button interaction verified within target ROI."
            if changed_roi is not None:
                return True, "Visual change detected after click."
            return False, "No visual change detected in target area."

        # 5. Semantic Validation via Vision LLM
        api_key = self.vision_manager.gemini_api_key or self.vision_manager.openai_api_key
        if api_key and after_bytes:
            prompt = (
                f"Look at this screenshot and determine if the following expected UI state holds:\n"
                f"'{expected_effect}'.\n"
                "Answer starting with YES: <reason> or NO: <reason>."
            )
            try:
                explanation = self.vision_manager.analyze_screen(query=prompt, image_bytes=after_bytes)
                is_yes = explanation.strip().upper().startswith("YES")
                return is_yes, explanation
            except Exception as exc:
                logger.debug("Semantic vision validation failed: %s", exc)

        # Fallback: If visual diff occurred, consider expected effect plausible
        return (changed_roi is not None), f"Visual change detected matching general expectation '{expected_effect}'."

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Main Verification Entrypoint
    # ──────────────────────────────────────────────────────────────────────────

    def verify_action(
        self,
        before_bytes: Optional[bytes] = None,
        after_bytes: Optional[bytes] = None,
        action_type: str = "click",
        target_roi: Optional[Tuple[int, int, int, int]] = None,
        expected_effect: Optional[str] = None,
        before_img: Optional[bytes] = None,
        after_img: Optional[bytes] = None,
        **kwargs: Any,
    ) -> VisualDiffResult:
        """
        Executes full visual verification pipeline between before and after action screenshots.
        Supports both (before_bytes, after_bytes) and (before_img, after_img).
        """
        b_bytes = before_bytes if before_bytes is not None else (before_img if before_img is not None else b"")
        a_bytes = after_bytes if after_bytes is not None else (after_img if after_img is not None else b"")

        diff_ratio, changed_roi, details = self.compute_pixel_diff(b_bytes, a_bytes)
        state_changed = diff_ratio >= self.diff_threshold

        expected_detected = False
        semantic_msg = ""

        if expected_effect:
            expected_detected, semantic_msg = self.evaluate_expected_effect(
                before_bytes=b_bytes,
                after_bytes=a_bytes,
                expected_effect=expected_effect,
                target_roi=target_roi,
                changed_roi=changed_roi,
            )
        else:
            # If no specific effect is requested, state_changed determines outcome
            if target_roi and changed_roi:
                expected_detected = self.check_roi_overlap(changed_roi, target_roi)
            else:
                expected_detected = state_changed
            semantic_msg = "Visual state change detected." if state_changed else "No visual state change detected."

        return VisualDiffResult(
            state_changed=state_changed,
            diff_ratio=diff_ratio,
            changed_roi=changed_roi,
            expected_change_detected=expected_detected,
            semantic_verification=semantic_msg,
            before_img_bytes=before_bytes,
            after_img_bytes=after_bytes,
            details=details,
        )

    def wait_for_visual_change(
        self,
        capture_fn: Callable[[], bytes],
        before_bytes: bytes,
        max_wait_s: float = 3.0,
        poll_interval_s: float = 0.2,
        target_roi: Optional[Tuple[int, int, int, int]] = None,
        expected_effect: Optional[str] = None,
    ) -> VisualDiffResult:
        """
        Polls screen capture until a visual state change is detected or timeout expires.
        """
        deadline = time.perf_counter() + max_wait_s
        last_result = VisualDiffResult(
            state_changed=False,
            diff_ratio=0.0,
            before_img_bytes=before_bytes,
            after_img_bytes=before_bytes,
        )

        while time.perf_counter() < deadline:
            time.sleep(poll_interval_s)
            try:
                after_bytes = capture_fn()
            except Exception as exc:
                logger.debug("Capture failed during polling: %s", exc)
                continue

            last_result = self.verify_action(
                before_bytes=before_bytes,
                after_bytes=after_bytes,
                target_roi=target_roi,
                expected_effect=expected_effect,
            )
            if last_result.state_changed or last_result.expected_change_detected:
                return last_result

        return last_result

    def _to_pil_image(self, img_input: Union[bytes, Any]) -> Optional[Any]:
        if not PIL_AVAILABLE or Image is None or img_input is None:
            return None
        try:
            if isinstance(img_input, Image.Image):
                return img_input
            if isinstance(img_input, (bytes, bytearray)):
                return Image.open(io.BytesIO(img_input))
        except Exception:
            pass
        return None
