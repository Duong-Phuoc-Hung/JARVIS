"""
build.py
========
Main executable packaging entrypoint for JARVIS Personal AI Assistant.
Usage:
    python build.py
"""
import sys
from scripts.build_exe import main

if __name__ == "__main__":
    sys.exit(main())
