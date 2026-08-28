"""
jarvis/skills/browser_control/__init__.py
==========================================
Browser Control skill: điều khiển Chrome bằng giọng nói.

Lệnh thoại:
  "JARVIS, mở YouTube"
  "Tìm kiếm tin tức công nghệ hôm nay"
  "Chụp ảnh trang này"
  "Kéo xuống"
  "Click vào nút Đăng nhập"
  "Trích xuất nội dung bài báo này"
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.skills.browser_control")

_BROWSER: Any | None = None
_QUICK_URLS: dict[str, str] = {
    "youtube":   "https://www.youtube.com",
    "google":    "https://www.google.com",
    "facebook":  "https://www.facebook.com",
    "gmail":     "https://mail.google.com",
    "github":    "https://github.com",
    "chatgpt":   "https://chat.openai.com",
    "gemini":    "https://gemini.google.com",
    "shopee":    "https://shopee.vn",
    "lazada":    "https://www.lazada.vn",
    "vnexpress": "https://vnexpress.net",
    "tuoitre":   "https://tuoitre.vn",
    "dantri":    "https://dantri.com.vn",
    "tgdd":      "https://www.thegioididong.com",
}


def _get_browser():
    global _BROWSER
    if _BROWSER is None:
        from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig
        cfg = BrowserConfig(headless=False, slow_mo_ms=50)
        _BROWSER = BrowserCDPController(config=cfg, is_mock=False)
        _BROWSER.launch()
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
    """
    Browser Control skill — điều khiển Chrome bằng giọng nói.

    Actions:
      open       - Mở URL hoặc trang web nhanh (youtube, github...)
      navigate   - Điều hướng đến URL bất kỳ
      search     - Tìm kiếm Google
      click      - Click vào phần tử (CSS selector hoặc text)
      type       - Gõ văn bản vào form
      screenshot - Chụp ảnh màn hình trình duyệt
      extract    - Trích xuất nội dung trang thành Markdown
      scroll     - Cuộn trang
      close      - Đóng trình duyệt
    """
    act = action.lower().strip()

    try:
        browser = _get_browser()

        if act == "open":
            # Resolve quick URL aliases
            target = url or query
            resolved = _QUICK_URLS.get(target.lower().rstrip("/"), target)
            if not resolved.startswith("http"):
                resolved = f"https://{resolved}"
            page = browser.navigate(resolved)
            msg = f"🌐 Đã mở: **{page.title}**\n📍 {page.url}"
            return {"data": {"text": msg, "url": page.url, "title": page.title, "success": True}, "output": msg}

        elif act == "navigate":
            target = url or query
            page = browser.navigate(target)
            msg = f"🌐 Đã điều hướng đến: **{page.title}**\n📍 {page.url}"
            return {"data": {"text": msg, "url": page.url, "success": True}, "output": msg}

        elif act == "search":
            if not query:
                return {"data": {"text": "Vui lòng cung cấp query để tìm kiếm.", "success": False}, "output": "Thiếu query"}
            page = browser.search_google(query)
            msg = f"🔍 Đang tìm kiếm: **{query}**\n📍 {page.url}"
            return {"data": {"text": msg, "query": query, "url": page.url, "success": True}, "output": msg}

        elif act == "click":
            if not selector:
                return {"data": {"text": "Vui lòng cung cấp selector hoặc text để click.", "success": False}, "output": "Thiếu selector"}
            ok = browser.click(selector)
            msg = f"{'✅' if ok else '❌'} Click: **{selector}**"
            return {"data": {"text": msg, "selector": selector, "success": ok}, "output": msg}

        elif act == "type":
            if not selector or not text:
                return {"data": {"text": "Cần cả selector và text.", "success": False}, "output": "Thiếu thông tin"}
            ok = browser.type_text(selector, text)
            msg = f"⌨️ Đã gõ vào [{selector}]: **{text[:40]}{'...' if len(text) > 40 else ''}**"
            return {"data": {"text": msg, "success": ok}, "output": msg}

        elif act == "screenshot":
            path = browser.screenshot(filename)
            if path:
                msg = f"📸 Ảnh chụp trình duyệt: `{path}`"
                return {"data": {"text": msg, "path": path, "success": True}, "output": msg}
            msg = "❌ Không chụp được ảnh."
            return {"data": {"text": msg, "success": False}, "output": msg}

        elif act == "extract":
            content = browser.extract_content_as_markdown()
            url_now = browser.get_current_url()
            preview = content[:200] + "..." if len(content) > 200 else content
            msg = f"📄 Nội dung từ `{url_now}`:\n\n{preview}"
            return {"data": {"text": msg, "content": content, "url": url_now, "success": bool(content)}, "output": msg}

        elif act == "scroll":
            ok = browser.scroll(direction, amount)
            msg = f"📜 Đã cuộn {'xuống' if direction == 'down' else 'lên'} {amount}px"
            return {"data": {"text": msg, "success": ok}, "output": msg}

        elif act == "key":
            ok = browser.press_key(key)
            msg = f"⌨️ Đã nhấn phím: **{key}**"
            return {"data": {"text": msg, "success": ok}, "output": msg}

        elif act in ("close", "exit", "quit"):
            browser.close()
            global _BROWSER
            _BROWSER = None
            msg = "🔴 Trình duyệt đã đóng."
            return {"data": {"text": msg, "success": True}, "output": msg}

        else:
            msg = f"Hành động '{act}' không hỗ trợ. Thử: open, search, click, type, screenshot, extract, scroll, close."
            return {"data": {"text": msg, "success": False}, "output": msg}

    except Exception as exc:
        log.error("Browser skill error: %s", exc)
        err = f"❌ Lỗi browser: {exc}"
        return {"data": {"text": err, "success": False}, "output": err}
