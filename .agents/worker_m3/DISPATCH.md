## 2026-08-24T02:38:07Z
You are the Worker implementing Milestone M3: Web Browser Automation Agent for the JARVIS Autonomous Agentic Superpower upgrade.
Your assigned working directory is `d:/Software GitCode/JARVIS/.agents/worker_m3`.
You MUST read `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md`, `d:/Software GitCode/JARVIS/PROJECT.md`, and `d:/Software GitCode/JARVIS/.agents/explorer_survey_3/handoff.md`.

Exclusively Owned Files:
- `jarvis/browser/__init__.py`
- `jarvis/browser/models.py`
- `jarvis/browser/driver.py`
- `jarvis/browser/session.py`
- `jarvis/browser/actions.py`
- `jarvis/browser/scraper.py`
- `jarvis/browser/agent.py`

Key Specifications:
1. Multi-Tier Browser Driver Hierarchy:
   - `BaseBrowserDriver`: Abstract driver contract (launch, close, navigate, click, type_text, select_option, wait_for_selector, evaluate_script, get_html, get_text, capture_page_screenshot, get_cookies, set_cookies).
   - `PlaywrightBrowserDriver` (Tier 1): Uses Playwright if installed.
   - `CDPBrowserDriver` (Tier 2): Chrome DevTools Protocol via WebSocket.
   - `HttpScrapingDriver` (Tier 3): Zero-browser fallback using `requests.Session` + `html.parser` / regex.
   - `MockBrowserDriver` (Tier 4): In-memory mock driver with simulated DOM nodes for 100% reliable headless CI/CD testing.
2. BrowserSessionManager:
   - Serializes and deserializes cookies, session tokens, and local storage to JSON / SQLite for persistent sessions.
3. WebScraper & Actions:
   - HTML to clean Markdown converter, structured data extractor, HTML table parser.
   - Form automation: fills text inputs, selects dropdowns, submits forms.
   - File download handler with progress tracking.
   - Price comparison aggregator: scrapes multiple stores and structures comparison items.
4. BrowserAgent:
   - High-level coordinator: `open_and_search`, `scrape_url`, `compare_prices`, `fill_form`, `download_resource`, `execute_workflow`.
