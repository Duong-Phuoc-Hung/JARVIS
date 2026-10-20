"""
Main execution entry point: python -m jarvis
Provides main() for CLI/console entry and main_tray() for GUI/tray entry.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence

from jarvis.cli import main

__all__ = ["main", "main_tray"]


def main_tray(argv: Sequence[str] | None = None) -> int:
    """
    Launch JARVIS directly in Windows System Tray mode.
    Entrypoint for gui-scripts: pyproject.toml [project.gui-scripts] jarvis-tray = "jarvis.__main__:main_tray".
    """
    if argv is None:
        passed = sys.argv[1:]
        cmd = ["--tray"] + [arg for arg in passed if arg != "--tray"]
    else:
        cmd = ["--tray"] + [arg for arg in argv if arg != "--tray"]
    return main(cmd)


if __name__ == "__main__":
    sys.exit(main())
