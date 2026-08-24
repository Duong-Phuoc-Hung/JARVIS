"""
jarvis/automation/gui_actor.py
==============================
Vision-Driven GUI Actor with Verification & Self-Healing Retries.

Coordinates:
- ComputerUseVision: 1000x1000 coordinate grounding & UI element detection.
- ComputerController: Mouse, keyboard, and OS window manipulation.
- VisualVerifier: Pre/post-action visual diffing and semantic state transition validation.

Features:
- `click_element`: Locates target UI element by query, clicks, and validates visual state transition.
- `type_into_element`: Focuses element, clears existing text (optional), types Unicode string, and verifies.
- `drag_element`: Drags from source element to target element with smooth motion.
- `hover_element`: Moves cursor to target element.
- `perform_verified_action`: General-purpose verified execution loop.
- Self-Healing Retries: Automatically adjusts click duration, applies coordinate jitter,
  and attempts double-click or window focus if no visual delta is detected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from jarvis.automation.control import ComputerController
from jarvis.vision.computer_use import BoundingBox, ComputerUseVision, UIElement
from jarvis.vision.screen import ScreenVisionManager
from jarvis.vision.visual_verifier import VisualDiffResult, VisualVerifier

logger = logging.getLogger("jarvis.automation.gui_actor")


@dataclass
class GUIActionResult:
    """Telemetry report for an executed vision-guided GUI action."""
    action: str
    target_query: str
    success: bool
    element_found: bool = False
    grounded_element: Optional[UIElement] = None
    target_pixel_pos: Optional[Tuple[int, int]] = None
    verification: Optional[VisualDiffResult] = None
    retries_used: int = 0
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0

    @property
    def element(self) -> Optional[UIElement]:
        """Convenience alias for grounded_element."""
        return self.grounded_element

    @property
    def visual_result(self) -> Optional[VisualDiffResult]:
        """Convenience alias for verification."""
        return self.verification

    @property
    def error(self) -> Optional[str]:
        """Convenience alias for error_message."""
        return self.error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target_query": self.target_query,
            "success": self.success,
            "element_found": self.element_found,
            "grounded_element": self.grounded_element.to_dict() if self.grounded_element else None,
            "target_pixel_pos": list(self.target_pixel_pos) if self.target_pixel_pos else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "retries_used": self.retries_used,
            "error_message": self.error_message,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


class GUIActor:
    """
    High-level Vision-Guided GUI Actor.
    Dispatches OS clicks, text entry, and drag operations by grounding on-screen UI elements,
    then verifies visual outcomes and self-heals against dead clicks.
    """

    def __init__(
        self,
        computer_use: Optional[ComputerUseVision] = None,
        controller: Optional[ComputerController] = None,
        verifier: Optional[VisualVerifier] = None,
        vision_manager: Optional[ScreenVisionManager] = None,
        vision: Optional[Any] = None,
        safety_gate: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        self.safety_gate = safety_gate
        self.vision_manager = vision_manager or ScreenVisionManager()
        cu = computer_use or vision
        if cu is not None and isinstance(cu, ScreenVisionManager):
            self.vision_manager = cu
            self.computer_use = ComputerUseVision(vision_manager=self.vision_manager)
        elif cu is not None and isinstance(cu, ComputerUseVision):
            self.computer_use = cu
        else:
            self.computer_use = cu or ComputerUseVision(vision_manager=self.vision_manager)
        self.controller = controller or ComputerController()
        self.verifier = verifier or VisualVerifier(vision_manager=self.vision_manager)
        self._action_history: List[GUIActionResult] = []

    @property
    def action_history(self) -> List[GUIActionResult]:
        """History of executed GUI actions."""
        return list(self._action_history)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Click Element with Self-Healing Verification
    # ──────────────────────────────────────────────────────────────────────────

    def click_element(
        self,
        query: str,
        double_click: bool = False,
        right_click: bool = False,
        verify: bool = True,
        max_retries: int = 2,
        expected_effect: Optional[str] = None,
        button: str = "left",
        clicks: int = 1,
        **kwargs: Any,
    ) -> bool:
        """
        Locates UI element by visual/text query, executes click, and validates visual change.
        
        If visual verification indicates a dead click (no state transition),
        triggers self-healing retries with offset jitter and increased duration.
        
        Args:
            query: Label, text, or visual description of target element (e.g. "Save", "Close", "Search").
            double_click: Whether to perform a double-click.
            right_click: Whether to perform a right-click.
            verify: Whether to perform pre/post screenshot visual verification.
            max_retries: Number of self-healing retries on verification failure.
            expected_effect: Optional expected effect string (e.g. "dialog_opened", "text_appeared:Saved").
            button: Mouse button ('left', 'right', 'middle').
            clicks: Number of clicks (1 for single, 2 for double).
            
        Returns:
            True if action succeeded and verified (if verify=True), False otherwise.
        """
        t0 = time.perf_counter()
        screen_w, screen_h = self.computer_use.get_screen_size()
        button_name = "right" if (right_click or button == "right") else button
        num_clicks = 2 if (double_click or clicks == 2) else clicks

        for attempt in range(max_retries + 1):
            # 1. Capture before-action screenshot
            before_bytes: bytes = b""
            if verify:
                try:
                    before_bytes, _ = self.vision_manager.capture_screenshot()
                except Exception as exc:
                    logger.debug("Failed to capture pre-action screenshot: %s", exc)

            # 2. Ground UI Element
            element = self.computer_use.locate_element(
                query=query,
                screenshot_bytes=before_bytes if before_bytes else None,
                screen_w=screen_w,
                screen_h=screen_h,
            )

            if not element:
                logger.warning("UI element matching '%s' could not be located on screen.", query)
                result = GUIActionResult(
                    action="click",
                    target_query=query,
                    success=False,
                    element_found=False,
                    retries_used=attempt,
                    error_message=f"Element '{query}' not found.",
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )
                self._record_result(result)
                return False

            # 3. Calculate Target Pixel Position (with self-healing jitter on retry)
            cx, cy = element.center_pixel(screen_w, screen_h)
            if attempt == 1:
                # Retry 1: Slight offset towards top-left quarter of element bbox
                left, top, right, bottom = element.bbox.to_pixel_coords(screen_w, screen_h)
                cx = left + max(1, (right - left) // 3)
                cy = top + max(1, (bottom - top) // 3)
                logger.info("Self-healing retry 1: Jittering click position to (%d, %d)", cx, cy)
            elif attempt >= 2:
                # Retry 2: Double-click fallback
                num_clicks = 2
                logger.info("Self-healing retry 2: Escalating to double-click at (%d, %d)", cx, cy)

            # 4. Dispatch Mouse Click
            self.controller.mouse_click(x=cx, y=cy, button=button_name, clicks=num_clicks)

            # 5. Verification Phase
            if not verify:
                result = GUIActionResult(
                    action="click",
                    target_query=query,
                    success=True,
                    element_found=True,
                    grounded_element=element,
                    target_pixel_pos=(cx, cy),
                    retries_used=attempt,
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )
                self._record_result(result)
                return True

            # Short wait for UI render / redraw
            time.sleep(0.2)

            after_bytes: bytes = b""
            try:
                after_bytes, _ = self.vision_manager.capture_screenshot()
            except Exception as exc:
                logger.debug("Failed to capture post-action screenshot: %s", exc)

            target_roi = element.bbox.to_pixel_coords(screen_w, screen_h)
            v_res = self.verifier.verify_action(
                before_bytes=before_bytes,
                after_bytes=after_bytes,
                action_type="click",
                target_roi=target_roi,
                expected_effect=expected_effect,
            )

            if v_res.state_changed or v_res.expected_change_detected:
                result = GUIActionResult(
                    action="click",
                    target_query=query,
                    success=True,
                    element_found=True,
                    grounded_element=element,
                    target_pixel_pos=(cx, cy),
                    verification=v_res,
                    retries_used=attempt,
                    execution_time_ms=(time.perf_counter() - t0) * 1000,
                )
                self._record_result(result)
                return True

            logger.warning(
                "Click on '%s' produced no visual state change (attempt %d/%d).",
                query, attempt + 1, max_retries + 1
            )

        # Retries exhausted
        result = GUIActionResult(
            action="click",
            target_query=query,
            success=False,
            element_found=True,
            grounded_element=element,
            target_pixel_pos=(cx, cy),
            verification=v_res,
            retries_used=max_retries,
            error_message="Action executed but visual state did not change after retries.",
            execution_time_ms=(time.perf_counter() - t0) * 1000,
        )
        self._record_result(result)
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Type Into Element with Verification
    # ──────────────────────────────────────────────────────────────────────────

    def type_into_element(
        self,
        query: str,
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        verify: bool = True,
        max_retries: int = 2,
    ) -> bool:
        """
        Focuses target input element, clears text if requested, types string, and verifies.
        """
        t0 = time.perf_counter()
        screen_w, screen_h = self.computer_use.get_screen_size()

        # 1. Focus element by clicking
        clicked = self.click_element(query=query, verify=False)
        if not clicked:
            result = GUIActionResult(
                action="type",
                target_query=query,
                success=False,
                element_found=False,
                error_message=f"Failed to focus element '{query}'.",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )
            self._record_result(result)
            return False

        time.sleep(0.1)

        # 2. Clear field if requested (Ctrl+A -> Backspace)
        if clear_first:
            self.controller.send_hotkey("ctrl", "a")
            time.sleep(0.05)
            self.controller.send_hotkey("backspace")
            time.sleep(0.05)

        # Capture pre-type screen for verification
        before_bytes = b""
        if verify:
            try:
                before_bytes, _ = self.vision_manager.capture_screenshot()
            except Exception:
                pass

        # 3. Inject text
        typed_ok = self.controller.type_text(text)

        if press_enter:
            time.sleep(0.05)
            self.controller.send_hotkey("enter")

        if not verify or not typed_ok:
            result = GUIActionResult(
                action="type",
                target_query=query,
                success=typed_ok,
                element_found=True,
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )
            self._record_result(result)
            return typed_ok

        # 4. Verify text entered
        time.sleep(0.2)
        after_bytes = b""
        try:
            after_bytes, _ = self.vision_manager.capture_screenshot()
        except Exception:
            pass

        v_res = self.verifier.verify_action(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            action_type="type",
            expected_effect=f"text_appeared:{text}",
        )

        success = v_res.state_changed or v_res.expected_change_detected
        result = GUIActionResult(
            action="type",
            target_query=query,
            success=success,
            element_found=True,
            verification=v_res,
            execution_time_ms=(time.perf_counter() - t0) * 1000,
        )
        self._record_result(result)
        return success

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Drag & Drop Element
    # ──────────────────────────────────────────────────────────────────────────

    def drag_element(
        self,
        source_query: str,
        target_query: str,
        verify: bool = True,
        max_retries: int = 2,
    ) -> bool:
        """
        Drags an element from source query position to target query position.
        """
        t0 = time.perf_counter()
        screen_w, screen_h = self.computer_use.get_screen_size()

        before_bytes = b""
        if verify:
            try:
                before_bytes, _ = self.vision_manager.capture_screenshot()
            except Exception:
                pass

        # Ground both elements
        src_elem = self.computer_use.locate_element(
            query=source_query, screenshot_bytes=before_bytes if before_bytes else None,
            screen_w=screen_w, screen_h=screen_h
        )
        tgt_elem = self.computer_use.locate_element(
            query=target_query, screenshot_bytes=before_bytes if before_bytes else None,
            screen_w=screen_w, screen_h=screen_h
        )

        if not src_elem or not tgt_elem:
            missing = source_query if not src_elem else target_query
            result = GUIActionResult(
                action="drag",
                target_query=f"{source_query} -> {target_query}",
                success=False,
                error_message=f"Element '{missing}' not found for drag operation.",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )
            self._record_result(result)
            return False

        sx, sy = src_elem.center_pixel(screen_w, screen_h)
        tx, ty = tgt_elem.center_pixel(screen_w, screen_h)

        # Execute Drag: Move to src -> Mouse down -> Smooth move to tgt -> Mouse up
        self.controller.mouse_move(sx, sy, smooth=False)
        time.sleep(0.05)

        # Primary drag via pyautogui or ctypes fallback
        try:
            import pyautogui  # type: ignore
            pyautogui.moveTo(sx, sy)
            pyautogui.dragTo(tx, ty, duration=0.4, button="left")
        except Exception:
            # Native fallback
            self.controller.mouse_click(sx, sy, button="left")
            time.sleep(0.1)
            self.controller.mouse_move(tx, ty, smooth=True)
            time.sleep(0.1)
            self.controller.mouse_click(tx, ty, button="left")

        if not verify:
            result = GUIActionResult(
                action="drag",
                target_query=f"{source_query} -> {target_query}",
                success=True,
                element_found=True,
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )
            self._record_result(result)
            return True

        time.sleep(0.2)
        after_bytes = b""
        try:
            after_bytes, _ = self.vision_manager.capture_screenshot()
        except Exception:
            pass

        v_res = self.verifier.verify_action(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            action_type="drag",
        )

        success = v_res.state_changed
        result = GUIActionResult(
            action="drag",
            target_query=f"{source_query} -> {target_query}",
            success=success,
            element_found=True,
            verification=v_res,
            execution_time_ms=(time.perf_counter() - t0) * 1000,
        )
        self._record_result(result)
        return success

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Hover Element
    # ──────────────────────────────────────────────────────────────────────────

    def hover_element(self, query: str) -> bool:
        """
        Moves mouse cursor over the center of target element.
        """
        screen_w, screen_h = self.computer_use.get_screen_size()
        element = self.computer_use.locate_element(query=query, screen_w=screen_w, screen_h=screen_h)
        if not element:
            return False
        cx, cy = element.center_pixel(screen_w, screen_h)
        return self.controller.mouse_move(cx, cy, smooth=True)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Generic Verified Action Runner
    # ──────────────────────────────────────────────────────────────────────────

    def perform_verified_action(
        self,
        action_fn: Callable[[], Any],
        expected_effect: Optional[str] = None,
        target_roi: Optional[Tuple[int, int, int, int]] = None,
        max_retries: int = 2,
    ) -> bool:
        """
        Wraps an arbitrary automation function with before/after screenshot capture
        and visual verification.
        """
        for attempt in range(max_retries + 1):
            before_bytes, _ = self.vision_manager.capture_screenshot()
            try:
                action_fn()
            except Exception as exc:
                logger.warning("Action execution failed: %s", exc)
                return False

            time.sleep(0.2)
            after_bytes, _ = self.vision_manager.capture_screenshot()

            v_res = self.verifier.verify_action(
                before_bytes=before_bytes,
                after_bytes=after_bytes,
                target_roi=target_roi,
                expected_effect=expected_effect,
            )

            if v_res.state_changed or v_res.expected_change_detected:
                return True

        return False

    def _record_result(self, result: GUIActionResult) -> None:
        self._action_history.append(result)
        if len(self._action_history) > 100:
            self._action_history.pop(0)
