"""
jarvis/ui/terminal/logo.py
============================
Deterministic, hard-coded J.A.R.V.I.S. ASCII banner. No figlet/pyfiglet
dependency. Three renditions are chosen automatically:

  - WIDE:  full block-letter Unicode banner (>=78 columns, UTF-8-capable).
  - NARROW: compact one-line Unicode banner (60-77 columns).
  - PLAIN: ASCII-only banner (non-UTF-8 stdout encoding, e.g. legacy
    cp1252/cp437 consoles, or width < 60).
"""
from __future__ import annotations

from jarvis.ui.terminal.console import supports_unicode, terminal_width
from jarvis.ui.terminal.theme import TerminalTheme

_WIDE_LOGO = r"""
        ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
        ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
        ██║███████║██████╔╝██║   ██║██║███████╗
   ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
   ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
    ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
""".strip("\n")

_NARROW_LOGO = "» J . A . R . V . I . S . «"

_PLAIN_LOGO = r"""
        _____   ___   ______  _    _  _____   _____
       |     | / _ \ |  __  || |  | ||_   _| /  ___|
       | | | || |_| || |__| || |  | |  | |   | |___
       | | | ||  _  ||  __  || |  | |  | |   \___  \
       | |_| || | | || |  | || |__| | _| |_   ___| |
       |_____||_| |_||_|  |_| \____/ |_____| |_____/
""".strip("\n")

_SUBTITLE = "J.A.R.V.I.S. // INFOSEC EDITION"
_TAGLINE = "JUST A RATHER VERY INTELLIGENT SYSTEM"


def render_logo(theme: TerminalTheme, width: int | None = None) -> list[str]:
    """Returns the banner as a list of pre-styled lines, picking the widest
    rendition that fits and is safely encodable on this console."""
    w = width if width is not None else terminal_width()
    unicode_ok = supports_unicode()

    if unicode_ok and w >= 78:
        body = _WIDE_LOGO
    elif unicode_ok and w >= 60:
        body = _NARROW_LOGO
    else:
        body = _PLAIN_LOGO

    lines = [theme.logo(line) for line in body.split("\n")]
    lines.append("")
    lines.append(theme.header(_SUBTITLE.center(w) if w else _SUBTITLE))
    lines.append(theme.dim(_TAGLINE.center(w) if w else _TAGLINE))
    return lines
