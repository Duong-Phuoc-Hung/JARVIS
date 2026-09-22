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

from jarvis.core.models import ActionResult, ActionStatus

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
class VMActionResult(ActionResult):
    vm_name: str = ""
    hypervisor: str = ""
    state: str = ""
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

    def _check_binary(self, hypervisor: str) -> str | None:
        """Resolves executable path or returns None if not installed."""
        if hypervisor == HypervisorType.VMWARE.value:
            return shutil.which(self.vmrun_path)
        return shutil.which(self.vboxmanage_path)

    def start_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
        gui_mode: str = "nogui",
    ) -> ActionResult:
        """Starts the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        exe_path = self._check_binary(hyp)
        if not exe_path:
            if self.dry_run:
                log.info("VM [%s] started under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
                return ActionResult(
                    action_name=f"vm.{hyp}.start",
                    success=True,
                    status=ActionStatus.SUCCESS,
                    code="OK",
                    message=f"VM {vm_name} started successfully",
                    retryable=False,
                    data={
                        "vm_name": vm_name,
                        "hypervisor": hyp,
                        "state": VMState.RUNNING.value,
                        "return_code": 0,
                    },
                )
            log.warning("Hypervisor CLI not found for '%s'", hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.start",
                success=False,
                status=ActionStatus.ERROR,
                code="TOOL_NOT_FOUND",
                message=f"Hypervisor binary for '{hyp}' is not installed or not in PATH.",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.STOPPED.value,
                },
            )

        if self.dry_run:
            log.info("VM [%s] started under hypervisor [%s] (dry-run)", vm_name, hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.start",
                success=True,
                status=ActionStatus.SUCCESS,
                code="OK",
                message=f"VM {vm_name} started successfully",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.RUNNING.value,
                    "return_code": 0,
                },
            )

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "start", vm_name, gui_mode]
            else:
                cmd = [self.vboxmanage_path, "startvm", vm_name, "--type", "headless" if gui_mode == "nogui" else "gui"]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return ActionResult(
                action_name=f"vm.{hyp}.start",
                success=success,
                status=ActionStatus.SUCCESS if success else ActionStatus.ERROR,
                code="OK" if success else "VM_START_FAILED",
                message=proc.stdout if success else (proc.stderr or f"Failed to start VM {vm_name}"),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.RUNNING.value if success else VMState.STOPPED.value,
                    "return_code": proc.returncode,
                },
            )
        except Exception as exc:
            log.error("Failed to start VM %s: %s", vm_name, exc)
            return ActionResult(
                action_name=f"vm.{hyp}.start",
                success=False,
                status=ActionStatus.ERROR,
                code="VM_EXCEPTION",
                message=str(exc),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.UNKNOWN.value,
                },
            )

    def stop_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
        mode: str = "soft",
    ) -> ActionResult:
        """Stops the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        exe_path = self._check_binary(hyp)
        if not exe_path:
            if self.dry_run:
                log.info("VM [%s] stopped under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
                return ActionResult(
                    action_name=f"vm.{hyp}.stop",
                    success=True,
                    status=ActionStatus.SUCCESS,
                    code="OK",
                    message=f"VM {vm_name} stopped successfully",
                    retryable=False,
                    data={
                        "vm_name": vm_name,
                        "hypervisor": hyp,
                        "state": VMState.STOPPED.value,
                        "return_code": 0,
                    },
                )
            log.warning("Hypervisor CLI not found for '%s'", hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.stop",
                success=False,
                status=ActionStatus.ERROR,
                code="TOOL_NOT_FOUND",
                message=f"Hypervisor binary for '{hyp}' is not installed or not in PATH.",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.STOPPED.value,
                },
            )

        if self.dry_run:
            log.info("VM [%s] stopped under hypervisor [%s] (dry-run)", vm_name, hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.stop",
                success=True,
                status=ActionStatus.SUCCESS,
                code="OK",
                message=f"VM {vm_name} stopped successfully",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.STOPPED.value,
                    "return_code": 0,
                },
            )

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "stop", vm_name, mode]
            else:
                action = "acpipowerbutton" if mode == "soft" else "poweroff"
                cmd = [self.vboxmanage_path, "controlvm", vm_name, action]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return ActionResult(
                action_name=f"vm.{hyp}.stop",
                success=success,
                status=ActionStatus.SUCCESS if success else ActionStatus.ERROR,
                code="OK" if success else "VM_STOP_FAILED",
                message=proc.stdout if success else (proc.stderr or f"Failed to stop VM {vm_name}"),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.STOPPED.value if success else VMState.RUNNING.value,
                    "return_code": proc.returncode,
                },
            )
        except Exception as exc:
            log.error("Failed to stop VM %s: %s", vm_name, exc)
            return ActionResult(
                action_name=f"vm.{hyp}.stop",
                success=False,
                status=ActionStatus.ERROR,
                code="VM_EXCEPTION",
                message=str(exc),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.UNKNOWN.value,
                },
            )

    def suspend_vm(
        self,
        vm_name: str,
        hypervisor: str | None = None,
    ) -> ActionResult:
        """Suspends the specified virtual machine."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        exe_path = self._check_binary(hyp)
        if not exe_path:
            if self.dry_run:
                log.info("VM [%s] suspended under hypervisor [%s] (simulated/dry-run)", vm_name, hyp)
                return ActionResult(
                    action_name=f"vm.{hyp}.suspend",
                    success=True,
                    status=ActionStatus.SUCCESS,
                    code="OK",
                    message=f"VM {vm_name} suspended successfully",
                    retryable=False,
                    data={
                        "vm_name": vm_name,
                        "hypervisor": hyp,
                        "state": VMState.SUSPENDED.value,
                    },
                )
            log.warning("Hypervisor CLI not found for '%s'", hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.suspend",
                success=False,
                status=ActionStatus.ERROR,
                code="TOOL_NOT_FOUND",
                message=f"Hypervisor binary for '{hyp}' is not installed or not in PATH.",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.STOPPED.value,
                },
            )

        if self.dry_run:
            log.info("VM [%s] suspended under hypervisor [%s]", vm_name, hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.suspend",
                success=True,
                status=ActionStatus.SUCCESS,
                code="OK",
                message=f"VM {vm_name} suspended successfully",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.SUSPENDED.value,
                },
            )

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "suspend", vm_name]
            else:
                cmd = [self.vboxmanage_path, "controlvm", vm_name, "pause"]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return ActionResult(
                action_name=f"vm.{hyp}.suspend",
                success=success,
                status=ActionStatus.SUCCESS if success else ActionStatus.ERROR,
                code="OK" if success else "VM_SUSPEND_FAILED",
                message=proc.stdout if success else (proc.stderr or f"Failed to suspend VM {vm_name}"),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "hypervisor": hyp,
                    "state": VMState.SUSPENDED.value if success else VMState.UNKNOWN.value,
                    "return_code": proc.returncode,
                },
            )
        except Exception as exc:
            log.error("Failed to suspend VM %s: %s", vm_name, exc)
            return ActionResult(
                action_name=f"vm.{hyp}.suspend",
                success=False,
                status=ActionStatus.ERROR,
                code="VM_EXCEPTION",
                message=str(exc),
                retryable=False,
                data={"vm_name": vm_name, "hypervisor": hyp, "state": VMState.UNKNOWN.value},
            )

    def snapshot_vm(
        self,
        vm_name: str,
        snapshot_name: str,
        hypervisor: str | None = None,
    ) -> ActionResult:
        """Creates a snapshot for the VM."""
        hyp = (hypervisor or self.default_hypervisor).lower()
        exe_path = self._check_binary(hyp)
        if not exe_path:
            if self.dry_run:
                log.info("VM [%s] snapshot [%s] created under hypervisor [%s] (simulated/dry-run)", vm_name, snapshot_name, hyp)
                return ActionResult(
                    action_name=f"vm.{hyp}.snapshot",
                    success=True,
                    status=ActionStatus.SUCCESS,
                    code="OK",
                    message=f"Snapshot '{snapshot_name}' created for VM {vm_name}",
                    retryable=False,
                    data={
                        "vm_name": vm_name,
                        "snapshot_name": snapshot_name,
                        "hypervisor": hyp,
                    },
                )
            log.warning("Hypervisor CLI not found for '%s'", hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.snapshot",
                success=False,
                status=ActionStatus.ERROR,
                code="TOOL_NOT_FOUND",
                message=f"Hypervisor binary for '{hyp}' is not installed or not in PATH.",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "snapshot_name": snapshot_name,
                    "hypervisor": hyp,
                },
            )

        if self.dry_run:
            log.info("VM [%s] snapshot [%s] created under hypervisor [%s]", vm_name, snapshot_name, hyp)
            return ActionResult(
                action_name=f"vm.{hyp}.snapshot",
                success=True,
                status=ActionStatus.SUCCESS,
                code="OK",
                message=f"Snapshot '{snapshot_name}' created for VM {vm_name}",
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "snapshot_name": snapshot_name,
                    "hypervisor": hyp,
                },
            )

        try:
            if hyp == HypervisorType.VMWARE.value:
                cmd = [self.vmrun_path, "-T", "ws", "snapshot", vm_name, snapshot_name]
            else:
                cmd = [self.vboxmanage_path, "snapshot", vm_name, "take", snapshot_name]

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_cflags)
            success = (proc.returncode == 0)
            return ActionResult(
                action_name=f"vm.{hyp}.snapshot",
                success=success,
                status=ActionStatus.SUCCESS if success else ActionStatus.ERROR,
                code="OK" if success else "VM_SNAPSHOT_FAILED",
                message=proc.stdout if success else (proc.stderr or f"Failed to take snapshot for VM {vm_name}"),
                retryable=False,
                data={
                    "vm_name": vm_name,
                    "snapshot_name": snapshot_name,
                    "hypervisor": hyp,
                    "return_code": proc.returncode,
                },
            )
        except Exception as exc:
            log.error("Failed to take snapshot for VM %s: %s", vm_name, exc)
            return ActionResult(
                action_name=f"vm.{hyp}.snapshot",
                success=False,
                status=ActionStatus.ERROR,
                code="VM_EXCEPTION",
                message=str(exc),
                retryable=False,
                data={"vm_name": vm_name, "snapshot_name": snapshot_name, "hypervisor": hyp},
            )
