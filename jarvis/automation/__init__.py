"""
jarvis.automation
=================
Workspace, OS Automation, Computer Control, Natural Language Shell, and Safety Subsystems.
"""

from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActionResult, GUIActor
from jarvis.automation.safety_gate import PendingConfirmation, SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.automation.vm import HypervisorType, VMActionResult, VMOrchestrator, VMState
from jarvis.automation.workspace import (
    WindowPlacementRecipe,
    WorkspaceRecipe,
    WorkspaceRecipeManager,
)

__all__ = [
    "ComputerController",
    "GUIActor",
    "GUIActionResult",
    "SafetyGate",
    "PendingConfirmation",
    "ShellAssistant",
    "VMOrchestrator",
    "VMActionResult",
    "HypervisorType",
    "VMState",
    "WorkspaceRecipeManager",
    "WorkspaceRecipe",
    "WindowPlacementRecipe",
]

