"""Legacy browser-control skill backed by the canonical browser adapter."""

from __future__ import annotations

import logging
import threading
from typing import Any

from jarvis.browser.models import BrowserDriverType, BrowserResultStatus

log = logging.getLogger("jarvis.skills.browser_control")

_BROWSER: Any | None = None
_BROWSER_LOCK = threading.Lock()
_LAST_LAUNCH_STATUS: BrowserResultStatus | None = None
_LAST_LAUNCH_ERROR_CODE: str | None = None
_LAST_LAUNCH_DRIVER_TYPE: BrowserDriverType | str | None = None
_QUICK_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "facebook": "https://www.facebook.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "gemini": "https://gemini.google.com",
    "shopee": "https://shopee.vn",
    "lazada": "https://www.lazada.vn",
    "vnexpress": "https://vnexpress.net",
    "tuoitre": "https://tuoitre.vn",
    "dantri": "https://dantri.com.vn",
    "tgdd": "https://www.thegioididong.com",
}


def _status_value(status: BrowserResultStatus | str) -> str:
    return status.value if isinstance(status, BrowserResultStatus) else str(status).upper()


def _driver_value(driver_type: BrowserDriverType | str | None) -> str | None:
    if isinstance(driver_type, BrowserDriverType):
        return driver_type.value
    return str(driver_type) if driver_type is not None else None


def _safe_error_message(status: BrowserResultStatus | str) -> str:
    value = _status_value(status)
    messages = {
        "TIMEOUT": "The browser action timed out.",
        "NOT_CONFIGURED": "The browser is not configured.",
        "UNAVAILABLE": "The browser driver is unavailable.",
        "AUTH_FAILED": "Browser authentication failed.",
        "RATE_LIMITED": "The browser request was rate limited.",
        "BLOCKED": "The browser action was blocked.",
        "CANCELLED": "The browser action was cancelled.",
        "DISCONNECTED": "The browser session is disconnected.",
    }
    return messages.get(value, "The browser action failed.")


def _response(
    *,
    success: bool,
    message: str,
    status: BrowserResultStatus | str,
    error_code: str | None = None,
    driver_type: BrowserDriverType | str | None = None,
    **data: Any,
) -> dict[str, Any]:
    """Build the stable top-level contract while retaining legacy nested fields."""

    status_value = _status_value(status)
    if not success and status_value == BrowserResultStatus.SUCCESS.value:
        status_value = BrowserResultStatus.ERROR.value
    elif success and status_value != BrowserResultStatus.SUCCESS.value:
        success = False
    error_code = None if success else (error_code or "BROWSER_ACTION_FAILED")
    safe_error = None if success else _safe_error_message(status_value)
    for sensitive_key in (
        "selector",
        "text",
        "value",
        "fields",
        "cookies",
        "password",
        "token",
    ):
        data.pop(sensitive_key, None)
    payload: dict[str, Any] = {
        "text": message,
        "success": success,
        "status": status_value,
        "error_code": error_code,
        "error_message": safe_error,
        "driver_type": _driver_value(driver_type),
    }
    payload.update(data)
    return {
        "success": success,
        "status": status_value,
        "error_code": error_code,
        "error_message": safe_error,
        "driver_type": _driver_value(driver_type),
        "data": payload,
        "output": message,
    }


def _browser_response(
    browser: Any,
    *,
    success: bool,
    message: str,
    error_code: str | None = None,
    **data: Any,
) -> dict[str, Any]:
    status = (
        BrowserResultStatus.SUCCESS
        if success
        else getattr(browser, "last_status", None) or BrowserResultStatus.ERROR
    )
    code = None if success else (
        error_code
        or getattr(browser, "last_error_code", None)
        or "BROWSER_ACTION_FAILED"
    )
    return _response(
        success=success,
        message=message,
        status=status,
        error_code=code,
        driver_type=getattr(browser, "driver_type", None),
        **data,
    )


def _get_browser() -> Any | None:
    """Return a launched browser, never caching a failed launch candidate."""

    global _BROWSER
    global _LAST_LAUNCH_DRIVER_TYPE
    global _LAST_LAUNCH_ERROR_CODE
    global _LAST_LAUNCH_STATUS
    with _BROWSER_LOCK:
        if _BROWSER is not None:
            return _BROWSER

        from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig

        candidate = BrowserCDPController(
            config=BrowserConfig(headless=False, slow_mo_ms=50),
            is_mock=False,
        )
        try:
            launched = candidate.launch()
        except Exception as exc:
            log.error("Browser skill launch failed (%s).", type(exc).__name__)
            launched = False
        if not launched:
            candidate_status = getattr(candidate, "last_status", None)
            _LAST_LAUNCH_STATUS = (
                candidate_status
                if isinstance(candidate_status, BrowserResultStatus)
                else BrowserResultStatus.UNAVAILABLE
            )
            candidate_code = getattr(candidate, "last_error_code", None)
            _LAST_LAUNCH_ERROR_CODE = (
                candidate_code
                if isinstance(candidate_code, str) and candidate_code
                else "BROWSER_DRIVER_UNAVAILABLE"
            )
            _LAST_LAUNCH_DRIVER_TYPE = getattr(candidate, "driver_type", None)
            try:
                candidate.close()
            except Exception:
                pass
            return None

        _BROWSER = candidate
        _LAST_LAUNCH_STATUS = None
        _LAST_LAUNCH_ERROR_CODE = None
        _LAST_LAUNCH_DRIVER_TYPE = None
        return _BROWSER


def execute(
    action: str = "search",
    url: str = "",
    query: str = "",
    selector: str = "",
    text: str = "",
    direction: str = "down",
    amount: int = 500,
    key: str = "Enter",
    filename: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a legacy browser command through the canonical browser layer."""

    global _BROWSER
    act = action.lower().strip()

    if act in ("close", "exit", "quit"):
        with _BROWSER_LOCK:
            browser = _BROWSER
            _BROWSER = None
        if browser is None:
            return _response(
                success=False,
                message="❌ Không có phiên trình duyệt đang hoạt động.",
                status=BrowserResultStatus.DISCONNECTED,
                error_code="BROWSER_NO_ACTIVE_SESSION",
            )
        driver_type = getattr(browser, "driver_type", None)
        try:
            closed = browser.close()
        except Exception as exc:
            log.error("Browser skill close failed (%s).", type(exc).__name__)
            return _response(
                success=False,
                message="❌ Không thể đóng trình duyệt.",
                status=BrowserResultStatus.ERROR,
                error_code="BROWSER_CLOSE_FAILED",
                driver_type=driver_type,
            )
        if closed is not True:
            return _browser_response(
                browser,
                success=False,
                message="❌ Không thể đóng trình duyệt.",
                error_code="BROWSER_CLOSE_FAILED",
            )
        return _response(
            success=True,
            message="🔴 Trình duyệt đã đóng.",
            status=BrowserResultStatus.SUCCESS,
            driver_type=driver_type,
        )

    if act == "search" and not query:
        return _response(
            success=False,
            message="Vui lòng cung cấp query để tìm kiếm.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_INPUT_REQUIRED",
        )
    if act in ("open", "navigate") and not (url or query):
        return _response(
            success=False,
            message="Vui lòng cung cấp URL.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_INPUT_REQUIRED",
        )
    if act in ("click", "wait") and not selector:
        return _response(
            success=False,
            message="Vui lòng cung cấp selector.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_INPUT_REQUIRED",
        )
    if act == "type" and (not selector or not text):
        return _response(
            success=False,
            message="Cần cả selector và nội dung cần nhập.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_INPUT_REQUIRED",
        )
    supported = {
        "open",
        "navigate",
        "search",
        "click",
        "type",
        "wait",
        "screenshot",
        "extract",
        "scroll",
        "key",
    }
    if act not in supported:
        return _response(
            success=False,
            message=f"Hành động '{act}' không được hỗ trợ.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_ACTION_UNSUPPORTED",
        )

    try:
        browser = _get_browser()
        if browser is None:
            return _response(
                success=False,
                message="❌ Trình duyệt hiện không khả dụng.",
                status=_LAST_LAUNCH_STATUS or BrowserResultStatus.UNAVAILABLE,
                error_code=(
                    _LAST_LAUNCH_ERROR_CODE or "BROWSER_DRIVER_UNAVAILABLE"
                ),
                driver_type=(
                    _LAST_LAUNCH_DRIVER_TYPE or BrowserDriverType.PLAYWRIGHT
                ),
            )

        if act == "open":
            target = url or query
            resolved = _QUICK_URLS.get(target.lower().rstrip("/"), target)
            if not resolved.startswith(("http://", "https://")):
                resolved = f"https://{resolved}"
            page = browser.navigate(resolved)
            if page.success:
                message = f"🌐 Đã mở: **{page.title}**\n📍 {page.url}"
                return _response(
                    success=True,
                    message=message,
                    status=page.status,
                    driver_type=page.driver_type,
                    url=page.url,
                    title=page.title,
                )
            return _response(
                success=False,
                message="❌ Không thể mở trang được yêu cầu.",
                status=page.status,
                error_code=page.error_code,
                driver_type=page.driver_type,
            )

        if act == "navigate":
            page = browser.navigate(url or query)
            if page.success:
                message = f"🌐 Đã điều hướng đến: **{page.title}**\n📍 {page.url}"
                return _response(
                    success=True,
                    message=message,
                    status=page.status,
                    driver_type=page.driver_type,
                    url=page.url,
                    title=page.title,
                )
            return _response(
                success=False,
                message="❌ Không thể điều hướng đến trang được yêu cầu.",
                status=page.status,
                error_code=page.error_code,
                driver_type=page.driver_type,
            )

        if act == "search":
            page = browser.search_google(query)
            if page.success:
                return _response(
                    success=True,
                    message="🔍 Đã mở trang kết quả tìm kiếm.",
                    status=page.status,
                    driver_type=page.driver_type,
                    url=page.url,
                )
            return _response(
                success=False,
                message="❌ Không thể mở trang kết quả tìm kiếm.",
                status=page.status,
                error_code=page.error_code,
                driver_type=page.driver_type,
            )

        if act == "click":
            ok = browser.click(selector)
            message = "✅ Đã click phần tử." if ok else "❌ Không thể click phần tử."
            return _browser_response(
                browser,
                success=ok,
                message=message,
                selector=selector,
            )

        if act == "type":
            ok = browser.type_text(selector, text)
            message = (
                "⌨️ Đã nhập dữ liệu vào trường được chọn."
                if ok
                else "❌ Không thể nhập dữ liệu vào trường được chọn."
            )
            # Never include the typed value in response data, output, or logs.
            return _browser_response(
                browser,
                success=ok,
                message=message,
                selector=selector,
            )

        if act == "wait":
            state = str(kwargs.get("state", "visible"))
            timeout = kwargs.get("timeout_ms")
            ok = browser.wait_for_selector(selector, state=state, timeout_ms=timeout)
            message = (
                "✅ Phần tử đã đạt trạng thái yêu cầu."
                if ok
                else "❌ Phần tử không đạt trạng thái yêu cầu."
            )
            return _browser_response(
                browser,
                success=ok,
                message=message,
                selector=selector,
                state=state,
            )

        if act == "screenshot":
            path = browser.screenshot(filename)
            if path:
                return _browser_response(
                    browser,
                    success=True,
                    message=f"📸 Ảnh chụp trình duyệt: `{path}`",
                    path=path,
                )
            return _browser_response(
                browser,
                success=False,
                message="❌ Không chụp được ảnh.",
                error_code="BROWSER_SCREENSHOT_FAILED",
            )

        if act == "extract":
            content = browser.extract_content_as_markdown()
            if content:
                url_now = browser.get_current_url()
                preview = content[:200] + "..." if len(content) > 200 else content
                message = f"📄 Nội dung từ `{url_now}`:\n\n{preview}"
                return _browser_response(
                    browser,
                    success=True,
                    message=message,
                    content=content,
                    url=url_now,
                )
            return _browser_response(
                browser,
                success=False,
                message="❌ Không đọc được nội dung trang.",
                error_code="BROWSER_CONTENT_READ_FAILED",
            )

        if act == "scroll":
            ok = browser.scroll(direction, amount)
            direction_label = {
                "down": "xuống",
                "up": "lên",
                "top": "lên đầu trang",
                "bottom": "xuống cuối trang",
            }.get(direction.lower().strip(), direction)
            message = (
                f"📜 Đã cuộn {direction_label} {amount}px."
                if ok
                else "❌ Không thể cuộn trang."
            )
            return _browser_response(browser, success=ok, message=message)

        ok = browser.press_key(key)
        message = f"⌨️ Đã nhấn phím: **{key}**" if ok else "❌ Không thể nhấn phím."
        return _browser_response(browser, success=ok, message=message)
    except Exception as exc:
        log.error("Browser skill action failed (%s).", type(exc).__name__)
        return _response(
            success=False,
            message="❌ Tác vụ browser thất bại.",
            status=BrowserResultStatus.ERROR,
            error_code="BROWSER_SKILL_ERROR",
        )
