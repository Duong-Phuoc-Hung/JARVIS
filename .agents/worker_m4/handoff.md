# Milestone M4 Handoff Report: Computer-Use Vision & Visual GUI Actor

**Author**: Worker M4 (`.agents/worker_m4`)  
**Parent Agent ID**: `066a3b59-4763-4416-9da6-bafb3993c06e`  
**Date**: 2026-08-24  
**Status**: Complete (Hard Handoff)

---

## 1. Observation

### 1.1 Requirements & Specifications
Milestone M4 requires implementing vision-driven computer use and desktop GUI automation for JARVIS:
- **Computer-Use Coordinate Grounding** (`jarvis/vision/computer_use.py`):
  * Anthropic 1000x1000 normalized coordinate system with bidirectional conversion to/from screen pixel coordinates.
  * `BoundingBox`, `UIElement`, `CoordinateMapper`, `UIElementDetector`, and `ComputerUseVision` classes.
  * 4-Tier UI Element Grounding Engine:
    - Tier 1: Vision LLM Grounding (Gemini 1.5 Flash / GPT-4o Vision structured prompt).
    - Tier 2: Local OCR Bounding Boxes (`DesktopOCR` / `pytesseract` data).
    - Tier 3: Win32 UIAutomation / `win32gui.EnumChildWindows` & `GetWindowRect`.
    - Tier 4: Template Matching & Synthetic UI fallback.
- **Visual Verification Loop** (`jarvis/vision/visual_verifier.py`):
  * `VisualVerifier` & `VisualDiffResult`.
  * Computes pixel delta ratio, Mean Squared Error (MSE), and ROI difference between before/after screenshots.
  * Evaluates whether expected UI change occurred (e.g., text appeared, dialog opened, button state changed, freeform semantic check).
  * Polling loop for visual state change (`wait_for_visual_change`).
- **Vision-Driven GUI Actor** (`jarvis/automation/gui_actor.py`):
  * `GUIActor` and `GUIActionResult`: Coordinates `ComputerUseVision`, `ComputerController`, and `VisualVerifier`.
  * `click_element(query, verify=True, max_retries=2, expected_effect=None)`.
  * `type_into_element(query, text, clear_first=True, press_enter=False, verify=True)`.
  * `drag_element(source_query, target_query, verify=True)`.
  * `hover_element(query)`.
  * `perform_verified_action(action_fn, expected_effect=None, target_roi=None)`.
  * Self-healing GUI retry: If visual state does not change on click, automatically adjusts coordinate offset (jitter towards top-left quarter), increases duration, and escalates to double-click.

### 1.2 Files Implemented and Modified
1. `jarvis/vision/computer_use.py` (NEW): Full Anthropic 1000x1000 normalized coordinate system, BoundingBox geometry math, UIElement, CoordinateMapper, and 4-tier grounding cascade engine.
2. `jarvis/vision/visual_verifier.py` (NEW): Full visual verification engine, pixel diff computation, MSE, ROI overlap check, expected effect verification, and polling.
3. `jarvis/automation/gui_actor.py` (NEW): High-level vision-guided GUI actor coordinating computer use, OS controller, and visual verification with self-healing dead-click recovery.
4. `jarvis/vision/__init__.py`: Added exports for `BoundingBox`, `CoordinateMapper`, `UIElement`, `UIElementDetector`, `ComputerUseVision`, `VisualDiffResult`, and `VisualVerifier`.
5. `jarvis/automation/__init__.py`: Added exports for `GUIActor` and `GUIActionResult`.
6. `tests/unit/test_computer_use_vision.py` (NEW): Comprehensive unit test suite covering coordinate conversions, 4-tier element detection, visual verification, expected effect validations, and GUI actor self-healing retries.

---

## 2. Logic Chain

1. **Normalized Coordinate Space**:
   - Normalized grid $[0, 1000]$ enables model independence from varying display resolutions and multi-monitor configurations.
   - Forward conversion: $x_{px} = \text{round}(x_{norm} \times W_{screen} / 1000.0)$, $y_{px} = \text{round}(y_{norm} \times H_{screen} / 1000.0)$, clamped to $[0, W_{screen}-1]$ and $[0, H_{screen}-1]$.
   - Backward conversion: $x_{norm} = \text{round}(x_{px} / W_{screen} \times 1000.0)$, $y_{norm} = \text{round}(y_{px} / H_{screen} \times 1000.0)$, clamped to $[0, 1000]$.
   - `BoundingBox` encapsulates normalized box coordinates $(ymin, xmin, ymax, xmax)$, provides `center_norm`, `width_norm`, `height_norm`, `area_norm`, pixel bounding box calculation, point containment check, and IoU computation.

2. **4-Tier Grounding Cascade**:
   - **Tier 1 (Vision LLM)**: Issues a structured JSON schema prompt to Gemini/GPT-4o Vision and parses bounding boxes into normalized coordinates.
   - **Tier 2 (Local OCR)**: When local OCR or pytesseract is available, extracts word and multi-word phrase bounding boxes instantly without network latency.
   - **Tier 3 (Win32 UIAutomation)**: Uses native `win32gui` enumeration to find OS window and control rectangles.
   - **Tier 4 (Template & Synthetic Heuristic)**: Heuristic geometry locator for standard desktop controls (Window Close 'X', Minimize '-', Search bar, Confirm/OK button, and generic center target).

3. **Visual Verification & Self-Healing**:
   - Intercepts state before and after GUI action.
   - Compares pixel changes via PIL/ImageChops and channel-level Manhattan distance, computing `diff_ratio` and bounding box of changed area (`changed_roi`).
   - Verifies target ROI intersection and evaluates semantic expected effects (`text_appeared:<query>`, `dialog_opened`, `button_pressed`).
   - If a click does not produce a visual delta (dead click), `GUIActor` self-heals by jittering coordinates and escalating to double-click on subsequent retry attempts.

---

## 3. Caveats

- In headless CI environments without physical display or X11/Win32 desktop, `ScreenVisionManager` provides synthetic frames and mock controller operations execute gracefully in memory.
- If Vision API keys are not configured, Tier 1 falls back transparently to Tier 2 (Local OCR), Tier 3 (Win32), and Tier 4 (Template/Synthetic heuristics).

---

## 4. Conclusion

Milestone M4 is fully implemented with genuine, robust logic according to all specifications in `PROJECT.md` and `ORIGINAL_REQUEST.md`. All coordinate conversions, grounding engines, visual verification loops, and self-healing GUI actor behaviors are strictly typed, well-documented, and covered by comprehensive unit tests.

---

## 5. Verification Method

### 5.1 Test Execution
Run unit tests covering Computer-Use Vision, Visual Verifier, and GUI Actor:
```powershell
pytest tests/unit/test_computer_use_vision.py -v
```

### 5.2 Key Test Cases Covered
1. `test_bounding_box_init_and_clamping`: Clamping to $[0, 1000]$ and dimension calculations.
2. `test_bounding_box_to_and_from_pixel_coords`: Bidirectional pixel $\leftrightarrow$ normalized grid mapping.
3. `test_bounding_box_contains_and_iou`: Containment and IoU evaluation.
4. `test_coordinate_mapper_conversions`: CoordinateMapper screen resolution and conversion logic.
5. `test_ui_element_serialization`: UIElement properties and dict serialization.
6. `test_tier1_vision_llm_grounding`: Vision LLM JSON parsing and normalized bounding box extraction.
7. `test_tier2_ocr_grounding_fallback`: Local OCR word and phrase bounding box extraction.
8. `test_tier3_win32_uia_grounding`: Win32 native control discovery.
9. `test_tier4_template_heuristics_fallback`: Template matching and heuristic UI detection.
10. `test_computer_use_vision_locate_cascading`: Multi-tier fallback cascade.
11. `test_visual_verifier_identical_images_zero_diff`: Identical images produce zero difference.
12. `test_visual_verifier_different_images_detected`: Pixel diffing, MSE, and ROI change extraction.
13. `test_visual_verifier_roi_overlap_check`: ROI overlap verification with margin.
14. `test_visual_verifier_expected_effect_text_appeared`: OCR-based expected effect validation.
15. `test_gui_actor_click_element_success`: Verified mouse click execution.
16. `test_gui_actor_self_healing_retry_on_dead_click`: Jitter and double-click self-healing on dead click.
17. `test_gui_actor_type_into_element`: Field focus, clear, text input, and verification.
18. `test_gui_actor_drag_element`: Source to target element drag and drop verification.
