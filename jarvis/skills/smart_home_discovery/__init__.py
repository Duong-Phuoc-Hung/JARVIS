"""
jarvis/skills/smart_home_discovery/__init__.py
===============================================
Smart Home Auto-Discovery skill: voice interface for SmartHomeDiscovery.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("jarvis.skills.smart_home_discovery")

_DISCOVERY = None


def _get_discovery():
    global _DISCOVERY
    if _DISCOVERY is None:
        from jarvis.smart_home.discovery import SmartHomeDiscovery
        _DISCOVERY = SmartHomeDiscovery()
    return _DISCOVERY


def execute(
    action: str = "list",
    subnet: str = "",
    target_ip: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Smart Home Auto-Discovery skill.

    Args:
        action: 'scan' | 'list' | 'probe' | 'status'
        subnet: Subnet to scan (e.g., '192.168.1.0/24')
        target_ip: Specific IP to probe
    """
    disc = _get_discovery()
    act = action.lower().strip()

    if act == "scan":
        if subnet:
            from jarvis.smart_home.discovery import DiscoveryConfig
            disc.config = DiscoveryConfig(scan_subnet=subnet)

        msg_start = f"🔍 Đang quét mạng {disc.config.scan_subnet}... (có thể mất 30-60 giây)"
        log.info("Smart home scan initiated via skill")

        # Run scan in background to avoid blocking
        import threading
        results_holder = {"devices": [], "done": False}

        def _scan():
            results_holder["devices"] = disc.scan_network()
            results_holder["done"] = True

        t = threading.Thread(target=_scan, daemon=True)
        t.start()
        t.join(timeout=15.0)  # Wait max 15s for initial results

        devices = results_holder["devices"]
        if not devices:
            devices = disc.get_registered_devices()
            msg = f"🏠 Không tìm thấy thiết bị mới. Đã đăng ký: {len(devices)} thiết bị."
        else:
            protocols = set(d.protocol for d in devices)
            msg = f"✅ Phát hiện {len(devices)} thiết bị: {', '.join(d.name for d in devices[:5])}"
            if len(devices) > 5:
                msg += f" (+{len(devices) - 5} khác)"

        device_list = [{"name": d.name, "ip": d.ip, "protocol": d.protocol} for d in devices]
        return {"data": {"devices": device_list, "count": len(devices), "text": msg, "success": True}, "output": msg}

    elif act == "list":
        devices = disc.get_registered_devices()
        if not devices:
            msg = "Chưa có thiết bị nào. Dùng action='scan' để quét mạng."
            return {"data": {"devices": [], "count": 0, "text": msg, "success": True}, "output": msg}

        lines = [f"🏠 {len(devices)} thiết bị đã đăng ký:"]
        for d in devices:
            status = "🟢" if d.is_online else "🔴"
            lines.append(f"  {status} {d.name} ({d.ip}) — {d.protocol}")
        msg = "\n".join(lines)
        device_list = [{"name": d.name, "ip": d.ip, "protocol": d.protocol, "online": d.is_online} for d in devices]
        return {"data": {"devices": device_list, "count": len(devices), "text": msg, "success": True}, "output": msg}

    elif act == "probe":
        if not target_ip:
            msg = "Vui lòng cung cấp target_ip để probe."
            return {"data": {"text": msg, "success": False}, "output": msg}

        device = (
            disc.probe_home_assistant(target_ip, 8123)
            or disc.probe_home_assistant(target_ip, 80)
            or disc.probe_tasmota(target_ip)
            or disc.probe_generic_http(target_ip, 80)
        )
        if device:
            msg = f"✅ Phát hiện thiết bị tại {target_ip}: {device.name} ({device.protocol})"
            return {"data": {"device": {"name": device.name, "protocol": device.protocol}, "text": msg, "success": True}, "output": msg}
        else:
            msg = f"Không tìm thấy thiết bị thông minh tại {target_ip}."
            return {"data": {"text": msg, "success": False}, "output": msg}

    elif act == "status":
        devices = disc.get_registered_devices()
        online = sum(1 for d in devices if disc.is_device_online(d.device_id))
        total = len(devices)
        msg = f"🏠 Smart Home: {online}/{total} thiết bị online"
        return {"data": {"online": online, "total": total, "text": msg, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: scan, list, probe, status."
        return {"data": {"text": msg, "success": False}, "output": msg}
