"""
jarvis/smart_home/discovery.py
==============================
Smart Home LAN Auto-Discovery: scans local network for smart devices
(Home Assistant, Tuya, Tasmota, generic HTTP) and auto-registers them.
No external dependencies required — uses stdlib socket and urllib.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("jarvis.smart_home.discovery")

_REGISTRY_FILE: Path | None = None  # resolved at runtime


@dataclass
class DiscoveredDevice:
    device_id: str
    name: str
    ip: str
    port: int
    protocol: str           # "home_assistant" | "tasmota" | "tuya" | "generic_http"
    capabilities: list[str] = field(default_factory=list)
    entity_id: str = ""
    last_seen: float = field(default_factory=time.time)
    is_online: bool = True


@dataclass
class DiscoveryConfig:
    scan_subnet: str = "192.168.1.0/24"
    scan_timeout_s: float = 1.5
    scan_ports: list[int] = field(default_factory=lambda: [80, 8080, 8123, 1880])
    auto_register: bool = True
    discovery_interval_s: float = 3600.0
    max_devices: int = 256


class SmartHomeDiscovery:
    """
    LAN auto-discovery for smart home devices.
    Scans subnet, probes known endpoints, and registers devices.
    """

    def __init__(
        self,
        config: DiscoveryConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or DiscoveryConfig()
        self.is_mock = is_mock
        self._devices: dict[str, DiscoveredDevice] = {}
        self._lock = threading.Lock()
        self._bg_thread: threading.Thread | None = None
        self._running = False
        self._load_registry()
        log.info(
            "SmartHomeDiscovery initialized (subnet=%s, %d devices cached)",
            self.config.scan_subnet,
            len(self._devices),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_network(self) -> list[DiscoveredDevice]:
        """
        Perform a full subnet scan to discover smart devices.
        Returns list of discovered devices.
        """
        if self.is_mock:
            log.info("SmartHomeDiscovery: mock scan returning empty list")
            return []

        cfg = self.config
        try:
            network = ipaddress.IPv4Network(cfg.scan_subnet, strict=False)
        except ValueError as exc:
            log.error("Invalid subnet '%s': %s", cfg.scan_subnet, exc)
            return []

        hosts = list(network.hosts())
        if len(hosts) > cfg.max_devices:
            hosts = hosts[:cfg.max_devices]

        log.info("Scanning %d hosts on %s...", len(hosts), cfg.scan_subnet)
        found: list[DiscoveredDevice] = []
        threads: list[threading.Thread] = []
        results_lock = threading.Lock()

        def _probe_host(ip_str: str) -> None:
            device = self._probe_all(ip_str)
            if device:
                with results_lock:
                    found.append(device)

        for host in hosts:
            t = threading.Thread(target=_probe_host, args=[str(host)], daemon=True)
            threads.append(t)
            t.start()
            # Stagger to avoid flooding
            if len(threads) % 32 == 0:
                for th in threads[-32:]:
                    th.join(timeout=cfg.scan_timeout_s + 0.5)

        for t in threads:
            t.join(timeout=cfg.scan_timeout_s + 1.0)

        if self.config.auto_register:
            self.register_devices(found)

        log.info("Scan complete: %d devices found", len(found))
        return found

    def _probe_all(self, ip: str) -> DiscoveredDevice | None:
        """Try probing a host with all known device fingerprints."""
        for port in self.config.scan_ports:
            if not self._port_open(ip, port, timeout=self.config.scan_timeout_s):
                continue
            device = (
                self.probe_home_assistant(ip, port)
                or self.probe_tasmota(ip)
                or self.probe_generic_http(ip, port)
            )
            if device:
                return device
        return None

    def _port_open(self, ip: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def probe_home_assistant(self, ip: str, port: int) -> DiscoveredDevice | None:
        """Probe for Home Assistant API endpoint."""
        try:
            url = f"http://{ip}:{port}/api/"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            resp = urllib.request.urlopen(req, timeout=self.config.scan_timeout_s)
            body = resp.read(512).decode("utf-8", errors="replace")
            if '"message"' in body and "API" in body:
                return DiscoveredDevice(
                    device_id=f"ha_{ip}",
                    name=f"Home Assistant ({ip})",
                    ip=ip, port=port,
                    protocol="home_assistant",
                    capabilities=["lights", "switches", "sensors", "climate"],
                    entity_id=f"ha_{ip.replace('.', '_')}",
                )
        except Exception:
            pass
        return None

    def probe_tasmota(self, ip: str) -> DiscoveredDevice | None:
        """Probe for Tasmota firmware endpoint."""
        for port in [80, 8080]:
            try:
                url = f"http://{ip}:{port}/cm?cmnd=Status"
                resp = urllib.request.urlopen(url, timeout=self.config.scan_timeout_s)
                body = resp.read(1024).decode("utf-8", errors="replace")
                if "Status" in body or "FriendlyName" in body:
                    name = "Tasmota Device"
                    try:
                        data = json.loads(body)
                        friendly = data.get("Status", {}).get("FriendlyName", [None])
                        if friendly and friendly[0]:
                            name = friendly[0]
                    except Exception:
                        pass
                    return DiscoveredDevice(
                        device_id=f"tasmota_{ip}",
                        name=name,
                        ip=ip, port=port,
                        protocol="tasmota",
                        capabilities=["power", "toggle", "status"],
                        entity_id=f"tasmota_{ip.replace('.', '_')}",
                    )
            except Exception:
                pass
        return None

    def probe_generic_http(self, ip: str, port: int) -> DiscoveredDevice | None:
        """Generic HTTP device probe (last resort)."""
        try:
            url = f"http://{ip}:{port}/"
            resp = urllib.request.urlopen(url, timeout=self.config.scan_timeout_s)
            body = resp.read(256).decode("utf-8", errors="replace").lower()
            smart_keywords = ["smart", "iot", "tuya", "shelly", "espressif", "esp8266", "esp32"]
            if any(kw in body for kw in smart_keywords):
                return DiscoveredDevice(
                    device_id=f"generic_{ip}",
                    name=f"Smart Device ({ip}:{port})",
                    ip=ip, port=port,
                    protocol="generic_http",
                    capabilities=["http_control"],
                    entity_id=f"generic_{ip.replace('.', '_')}",
                )
        except Exception:
            pass
        return None

    def register_devices(self, devices: list[DiscoveredDevice]) -> int:
        """Register discovered devices to the local registry."""
        count = 0
        with self._lock:
            for device in devices:
                self._devices[device.device_id] = device
                count += 1
        self._save_registry()
        log.info("Registered %d devices", count)
        return count

    def get_registered_devices(self) -> list[DiscoveredDevice]:
        with self._lock:
            return list(self._devices.values())

    def is_device_online(self, device_id: str) -> bool:
        with self._lock:
            device = self._devices.get(device_id)
        if not device:
            return False
        return self._port_open(device.ip, device.port, timeout=1.0)

    def get_online_count(self) -> int:
        return sum(1 for d in self.get_registered_devices() if self.is_device_online(d.device_id))

    # ------------------------------------------------------------------
    # Background Discovery
    # ------------------------------------------------------------------

    def start_background_scan(self) -> None:
        if self.is_mock or self._running:
            return
        self._running = True
        self._bg_thread = threading.Thread(
            target=self._bg_loop, daemon=True, name="smart-home-discovery"
        )
        self._bg_thread.start()
        log.info("Background smart home discovery started (interval=%ds)", int(self.config.discovery_interval_s))

    def stop(self) -> None:
        self._running = False
        if self._bg_thread:
            self._bg_thread.join(timeout=3.0)

    def _bg_loop(self) -> None:
        while self._running:
            try:
                self.scan_network()
            except Exception as exc:
                log.error("Background scan error: %s", exc)
            time.sleep(self.config.discovery_interval_s)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_registry(self) -> None:
        _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {did: asdict(d) for did, d in self._devices.items()}
            _REGISTRY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            log.warning("Smart home registry save error: %s", exc)

    def _load_registry(self) -> None:
        if not _REGISTRY_FILE.exists():
            return
        try:
            raw = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
            for did, d in raw.items():
                self._devices[did] = DiscoveredDevice(**{
                    k: v for k, v in d.items()
                    if k in DiscoveredDevice.__dataclass_fields__
                })
        except Exception as exc:
            log.warning("Smart home registry load error: %s", exc)


__all__ = ["SmartHomeDiscovery", "DiscoveryConfig", "DiscoveredDevice"]
