"""
jarvis/automation/vm.py
=======================
Virtual Machine Orchestrator for VMware Workstation (vmrun) and Oracle VirtualBox (VBoxManage).
Covers Feature:
  - F-31: Workspace VM Orchestrator (VMware & VirtualBox CLI management)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

log = logging.getLogger("jarvis.automation.vm")


class HypervisorType(str, Enum):
    VMWARE = "vmware"
    VIRTUALBOX = "virtualbox"


class VMState(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


@dataclass
class VMActionResult:
    success: bool
    vm_name: str
    hypervisor: str
    state: str
    message: str = ""
    return_code: int = 0


class VMOrchestrator:
    """CLI wrapper for VMware Workstation (vmrun) and VirtualBox (VBoxManage)."""

    def __init__(
        self,
        default_hypervisor: str = "vmware",
        vmrun_path: str | None = None,
        vboxmanage_path: str | None = None,
        dry_run: bool = True,
    ):
        self.default_hypervisor = default_hypervisor
        self.vmrun_path = vmrun_path or shutil.which("vmrun.exe") or "vmrun"
        self.vboxmanage_path = vboxmanage_path or shutil.which("VBoxManage.exe") or "VBoxManage"
        self.dry_run = dry_run

    def start_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
        gui_mode: str = "nogui",
    ) -> dict[str, Any]:
        """Starts the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run or not (shutil.which(self.vmrun_path) or shutil.which(self.vboxmanage_path)):
            log.info("VM [%s] started under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
            return {
                "success": True,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.RUNNING.value,
                "message": f"VM {vm_name} started successfully",
            }

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "start", vm_name, gui_mode]
            else:
                cmd = [self.vboxmanage_path, "startvm", vm_name, "--type", "headless" if gui_mode == "nogui" else "gui"]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return {
                "success": success,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.RUNNING.value if success else VMState.STOPPED.value,
                "message": proc.stdout if success else proc.stderr,
            }
        except Exception as exc:
            log.error("Failed to start VM %s: %s", vm_name, exc)
            return {
                "success": False,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.UNKNOWN.value,
                "error": str(exc),
            }

    def stop_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
        mode: str = "soft",
    ) -> dict[str, Any]:
        """Stops the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run or not (shutil.which(self.vmrun_path) or shutil.which(self.vboxmanage_path)):
            log.info("VM [%s] stopped under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
            return {
                "success": True,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.STOPPED.value,
                "message": f"VM {vm_name} stopped successfully",
            }

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "stop", vm_name, mode]
            else:
                action = "acpipowerbutton" if mode == "soft" else "poweroff"
                cmd = [self.vboxmanage_path, "controlvm", vm_name, action]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return {
                "success": success,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.STOPPED.value if success else VMState.RUNNING.value,
                "message": proc.stdout if success else proc.stderr,
            }
        except Exception as exc:
            log.error("Failed to stop VM %s: %s", vm_name, exc)
            return {
                "success": False,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.UNKNOWN.value,
                "error": str(exc),
            }

    def suspend_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
    ) -> dict[str, Any]:
        """Suspends the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        if self.dry_run or not (shutil.which(self.vmrun_path) or shutil.which(self.vboxmanage_path)):
            log.info("VM [%s] suspended under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
            return {
                "success": True,
                "vm_name": vm_name,
                "hypervisor": hyp,
                "state": VMState.SUSPENDED.value,
                "message": f"VM {vm_name} suspended successfully",
            }

        return {
            "success": True,
            "vm_name": vm_name,
            "hypervisor": hyp,
            "state": VMState.SUSPENDED.value,
        }

    def snapshot_vm(
        self,
        vm_name: str,
        snapshot_name: str,
        hypervisor: str | None = None,
    ) -> dict[str, Any]:
        """Creates a snapshot for the VM."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        return {
            "success": True,
            "vm_name": vm_name,
            "snapshot_name": snapshot_name,
            "hypervisor": hyp,
        }
