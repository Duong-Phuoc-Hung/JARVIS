"""
jarvis/automation/workspace.py
==============================
Workspace Recipe Manager for Multi-App & Multi-Monitor Developer Environments.
Covers Feature:
  - F-32: IDE & Terminal Workspace Prep (Cursor/VS Code & Windows Terminal recipes)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass, field, is_dataclass
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

    def register_recipe(self, name: str, recipe_dict: dict[str, Any] | WorkspaceRecipe) -> None:
        """Registers or updates a workspace recipe."""
        if is_dataclass(recipe_dict) and not isinstance(recipe_dict, type):
            self.recipes[name] = asdict(recipe_dict)
        else:
            self.recipes[name] = recipe_dict  # type: ignore

    def prepare_workspace(
        self, recipe: str | WorkspaceRecipe | dict[str, Any] = "ai_development"
    ) -> dict[str, Any]:
        """Launches configured IDE, terminal tabs, browser pages, and optional VM."""
        if isinstance(recipe, WorkspaceRecipe) or (is_dataclass(recipe) and not isinstance(recipe, type)):
            recipe_dict = asdict(recipe)
            recipe_name = getattr(recipe, "name", "custom")
            apps: list[str] = []
            if getattr(recipe, "ide", None):
                apps.append(recipe.ide)
            if hasattr(recipe, "background_apps") and recipe.background_apps:
                apps.extend(recipe.background_apps)
            urls: list[str] = []
            if hasattr(recipe, "browser_urls") and recipe.browser_urls:
                for u in recipe.browser_urls:
                    if isinstance(u, dict):
                        urls.append(u.get("url", ""))
                    elif isinstance(u, str):
                        urls.append(u)
            vm_name = getattr(recipe, "vm_to_start", None) or recipe_dict.get("vm")
        elif isinstance(recipe, dict):
            recipe_dict = recipe
            recipe_name = str(recipe_dict.get("name", "custom"))
            apps = recipe_dict.get("launched_apps", ["cursor.exe", "wt.exe", "spotify.exe"])
            urls = recipe_dict.get("urls", [])
            vm_name = recipe_dict.get("vm")
        else:
            recipe_name = str(recipe)
            cfg = self.recipes.get(
                recipe_name,
                {
                    "name": recipe_name,
                    "launched_apps": ["cursor.exe", "wt.exe", "spotify.exe"],
                },
            )
            apps = cfg.get("launched_apps", ["cursor.exe", "wt.exe", "spotify.exe"])
            urls = cfg.get("urls", [])
            vm_name = cfg.get("vm")

        # Launch apps
        for app in apps:
            if not app:
                continue
            try:
                if hasattr(os, "startfile") and sys.platform == "win32":
                    os.startfile(app)  # type: ignore
                else:
                    _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    subprocess.Popen([app], creationflags=_cflags)
            except Exception as exc:
                log.debug("App launch attempted for '%s': %s", app, exc)

        # Open URLs
        for url in urls:
            if not url:
                continue
            try:
                webbrowser.open(url)
            except Exception as exc:
                log.debug("Browser open attempted for '%s': %s", url, exc)

        # Optional VM start
        if vm_name and self.vm and hasattr(self.vm, "start_vm"):
            try:
                self.vm.start_vm(vm_name)
            except Exception as exc:
                log.warning("Could not auto-start VM '%s': %s", vm_name, exc)

        log.info("Workspace recipe '%s' prepared with apps: %s", recipe_name, apps)
        return {
            "success": True,
            "recipe": recipe_name,
            "launched_apps": apps,
            "urls": urls,
        }
