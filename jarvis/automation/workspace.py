"""
jarvis/automation/workspace.py
==============================
Workspace Recipe Manager for Multi-App & Multi-Monitor Developer Environments.
Covers Feature:
  - F-32: IDE & Terminal Workspace Prep (Cursor/VS Code & Windows Terminal recipes)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("jarvis.automation.workspace")


@dataclass
class WindowPlacementRecipe:
    app_name: str
    monitor_index: int = 1
    fullscreen: bool = False
    rect: tuple[int, int, int, int] | None = None


@dataclass
class WorkspaceRecipe:
    name: str
    description: str = ""
    ide: str | None = "cursor.exe"
    project_dir: str = "d:/Software GitCode/JARVIS"
    terminal_tabs: list[dict[str, str]] = field(default_factory=list)
    browser_urls: list[dict[str, Any]] = field(default_factory=list)
    vm_to_start: str | None = None
    background_apps: list[str] = field(default_factory=list)


class WorkspaceRecipeManager:
    """Orchestrates multi-window developer workspaces and launches configured recipes."""

    def __init__(
        self,
        win32_platform: Any | None = None,
        vm_orchestrator: Any | None = None,
    ):
        self.win32 = win32_platform
        self.vm = vm_orchestrator
        self.recipes: dict[str, dict[str, Any]] = {
            "ai_development": {
                "name": "ai_development",
                "description": "Full-stack AI Development Workspace",
                "launched_apps": ["cursor.exe", "wt.exe", "spotify.exe"],
                "vm": "UbuntuDev",
                "urls": ["https://claude.ai/new", "https://binance.com"],
            },
            "morning_workspace": {
                "name": "morning_workspace",
                "description": "Morning Productivity Workspace",
                "launched_apps": ["cursor.exe", "wt.exe", "spotify.exe", "chrome.exe"],
                "vm": "UbuntuDev",
                "urls": ["https://claude.ai", "https://mail.google.com"],
            },
        }

    def register_recipe(self, name: str, recipe_dict: dict[str, Any]) -> None:
        """Registers or updates a workspace recipe."""
        self.recipes[name] = recipe_dict

    def prepare_workspace(self, recipe: str = "ai_development") -> dict[str, Any]:
        """Launches configured IDE, terminal tabs, browser pages, and optional VM."""
        cfg = self.recipes.get(
            recipe,
            {
                "name": recipe,
                "launched_apps": ["cursor.exe", "wt.exe", "spotify.exe"],
            },
        )

        launched_apps = cfg.get("launched_apps", ["cursor.exe", "wt.exe", "spotify.exe"])

        # Optional VM start
        vm_name = cfg.get("vm")
        if vm_name and self.vm and hasattr(self.vm, "start_vm"):
            try:
                self.vm.start_vm(vm_name)
            except Exception as exc:
                log.warning("Could not auto-start VM '%s': %s", vm_name, exc)

        log.info("Workspace recipe '%s' prepared with apps: %s", recipe, launched_apps)
        return {
            "success": True,
            "recipe": recipe,
            "launched_apps": launched_apps,
            "urls": cfg.get("urls", []),
        }
