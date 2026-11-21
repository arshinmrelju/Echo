"""Low-level system probes used by the monitoring engine.

All functions here are synchronous and safe to run in a worker thread.
Hardware-specific capabilities (temperature, Windows Event Log) degrade to an
explicit "unavailable" result rather than inventing data.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import psutil

logger = logging.getLogger("echo.monitoring.collectors")

GIB = 1024 ** 3
EVENT_NS = "http://schemas.microsoft.com/win/2004/08/events/event"

# Relevant Windows System events. Deliberately an allowlist: dumping every
# System log entry would bury the signal and cause alert fatigue.
SYSTEM_EVENT_MAP: Dict[int, Dict[str, str]] = {
    41: {
        "severity": "critical",
        "title": "Unexpected shutdown",
        "description": "Windows did not shut down cleanly (Kernel-Power).",
    },
    1001: {
        "severity": "critical",
        "title": "System crash (bugcheck)",
        "description": "Windows recorded a bugcheck / blue-screen event.",
    },
    6008: {
        "severity": "warning",
        "title": "Unexpected shutdown recorded",
        "description": "The previous system shutdown was unexpected.",
    },
    6005: {
        "severity": "info",
        "title": "Windows started",
        "description": "The Windows Event Log service started.",
    },
    6006: {
        "severity": "info",
        "title": "Windows shut down cleanly",
        "description": "The Windows Event Log service stopped cleanly.",
    },
    7000: {
        "severity": "notice",
        "title": "Service failed to start",
        "description": "A Windows service could not start.",
    },
    7001: {
        "severity": "notice",
        "title": "Service dependency failure",
        "description": "A dependent service failed to start.",
    },
    7009: {
        "severity": "notice",
        "title": "Service start timeout",
        "description": "A service timed out while starting.",
    },
    7011: {
        "severity": "warning",
        "title": "Service did not respond",
        "description": "A service did not respond to a control request in time.",
    },
    7023: {
        "severity": "warning",
        "title": "Service terminated with an error",
        "description": "A Windows service stopped with an error.",
    },
    7031: {
        "severity": "warning",
        "title": "Service terminated unexpectedly",
        "description": "A Windows service was terminated unexpectedly.",
    },
    7034: {
        "severity": "warning",
        "title": "Service terminated unexpectedly",
        "description": "A Windows service was terminated unexpectedly.",
    },
    51: {
        "severity": "warning",
        "title": "Disk error detected",
        "description": "A paging or disk I/O error was reported.",
    },
    153: {
        "severity": "warning",
        "title": "Disk I/O retry",
        "description": "A disk request was retried.",
    },
    129: {
        "severity": "warning",
        "title": "Disk reset",
        "description": "A disk was reset after an error.",
    },
    98: {
        "severity": "warning",
        "title": "Disk timeout",
        "description": "A disk I/O request timed out.",
    },
    140: {
        "severity": "warning",
        "title": "Disk timeout",
        "description": "A disk I/O request timed out.",
    },
}

APP_CRASH_EVENT_IDS = {1000, 1002}

_SYSTEM_EVENT_XPATH = (
    "*[System[(EventID=41 or EventID=1001 or EventID=6008 or EventID=6005 or "
    "EventID=6006 or EventID=7000 or EventID=7001 or EventID=7009 or "
    "EventID=7011 or EventID=7023 or EventID=7031 or EventID=7034 or "
    "EventID=51 or EventID=153 or EventID=129 or EventID=98 or EventID=140)]]"
)
_APPLICATION_EVENT_XPATH = (
    "*[System[Provider[@Name='Application Error' or @Name='Application Hang']]]"
)

if sys.platform == "win32":
    user32 = ctypes.windll.user32
else:  # pragma: no cover - non-Windows fallback
    user32 = None

_ENUM_PROC = (
    ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    if sys.platform == "win32"
    else None
)

_NOT_AVAILABLE_TEMP = {
    "available": False,
    "celsius": None,
    "source": None,
    "reason": "No hardware temperature sensor is exposed on this machine.",
    "checked_at": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CPU / memory / disk / battery / throughput
# ---------------------------------------------------------------------------


def _safe_cpu_frequency() -> Optional[float]:
    try:
        frequency = psutil.cpu_freq()
        if frequency and frequency.current:
            return round(float(frequency.current), 1)
    except (AttributeError, OSError):
        pass
    return None


def _disk_candidates(paths: List[str]) -> List[str]:
    if paths:
        return paths
    candidates: List[str] = []
    try:
        for partition in psutil.disk_partitions(all=False):
            if "cdrom" in (partition.opts or "").lower() or not partition.fstype:
                continue
            candidates.append(partition.mountpoint)
    except (AttributeError, OSError):
        pass
    if not candidates:
        system_drive = os.getenv("SystemDrive")
        candidates = [f"{system_drive}{os.sep}" if system_drive else os.path.abspath(os.sep)]
    return candidates[:8]


def collect_disks(paths: List[str]) -> List[Dict[str, Any]]:
    disks: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in _disk_candidates(paths):
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            usage = psutil.disk_usage(path)
        except (OSError, PermissionError):
            continue
        disks.append(
            {
                "path": path,
                "total_gb": round(usage.total / GIB, 1),
                "used_gb": round(usage.used / GIB, 1),
                "free_gb": round(usage.free / GIB, 1),
                "percent": round(float(usage.percent), 1),
            }
        )
    return disks


def collect_battery() -> Dict[str, Any]:
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, OSError):
        battery = None
    if battery is None:
        return {
            "present": False,
            "percent": None,
            "plugged": None,
            "seconds_left": None,
        }
    seconds_left = battery.secsleft
    if seconds_left in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        seconds_left = None
    return {
        "present": True,
        "percent": round(float(battery.percent), 1),
        "plugged": bool(battery.power_plugged),
        "seconds_left": int(seconds_left) if seconds_left is not None else None,
    }


def _top_processes(limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "status"]):
        try:
            info = proc.info
            memory = info.get("memory_info")
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "memory_mb": round(memory.rss / (1024 * 1024), 1) if memory else 0.0,
                    "status": info.get("status") or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda item: item["memory_mb"], reverse=True)
    return rows[:limit]


def collect_snapshot(top_process_count: int = 5, disk_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """Collect one point-in-time system sample. CPU percent is non-blocking."""
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    try:
        net = psutil.net_io_counters()
        net_rx = int(net.bytes_recv)
        net_tx = int(net.bytes_sent)
        net_packets_rx = int(net.packets_recv)
        net_packets_tx = int(net.packets_sent)
    except (AttributeError, OSError):
        net_rx = net_tx = net_packets_rx = net_packets_tx = 0

    try:
        boot_time = float(psutil.boot_time())
    except (AttributeError, OSError):
        boot_time = 0.0

    try:
        process_count = len(psutil.pids())
    except (AttributeError, OSError):
        process_count = 0

    return {
        "timestamp": now_iso(),
        "cpu": {
            "percent": round(float(psutil.cpu_percent(interval=None)), 1),
            "cores_logical": psutil.cpu_count(logical=True),
            "cores_physical": psutil.cpu_count(logical=False),
            "frequency_mhz": _safe_cpu_frequency(),
        },
        "memory": {
            "percent": round(float(memory.percent), 1),
            "used_gb": round(memory.used / GIB, 2),
            "available_gb": round(memory.available / GIB, 2),
            "total_gb": round(memory.total / GIB, 2),
            "swap_percent": round(float(swap.percent), 1),
        },
        "disks": collect_disks(disk_paths or []),
        "battery": collect_battery(),
        "network_io": {
            "bytes_recv": net_rx,
            "bytes_sent": net_tx,
            "packets_recv": net_packets_rx,
            "packets_sent": net_packets_tx,
        },
        "process_count": process_count,
        "top_processes": _top_processes(top_process_count),
        "boot_time": datetime.fromtimestamp(boot_time, tz=timezone.utc).isoformat()
        if boot_time
        else None,
        "uptime_seconds": round(max(0.0, time.time() - boot_time), 0) if boot_time else None,
        "platform": f"{platform.system()} {platform.release()}",
    }


# ---------------------------------------------------------------------------
# Network connectivity
# ---------------------------------------------------------------------------


def _split_target(target: str) -> Optional[tuple[str, int]]:
    host, sep, port_text = target.rpartition(":")
    if not sep or not host:
        return None
    try:
        port = int(port_text)
    except ValueError:
        return None
    if not 0 < port < 65536:
        return None
    return host.strip("[]"), port


def check_connectivity(targets: List[str], timeout: float) -> Dict[str, Any]:
    checked_at = now_iso()
    errors: List[str] = []
    for target in targets:
        parsed = _split_target(target)
        if parsed is None:
            errors.append(f"{target}: invalid host:port")
            continue
        host, port = parsed
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
            return {
                "online": True,
                "target": target,
                "latency_ms": latency_ms,
                "checked_at": checked_at,
                "errors": errors,
            }
        except OSError as exc:
            errors.append(f"{target}: {exc}")
    return {
        "online": False,
        "target": None,
        "latency_ms": None,
        "checked_at": checked_at,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Temperature (optional hardware bridge)
# ---------------------------------------------------------------------------

_TEMPERATURE_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$namespaces = @('root/LibreHardwareMonitor', 'root/OpenHardwareMonitor')
foreach ($ns in $namespaces) {
  $sensors = Get-CimInstance -Namespace $ns -ClassName Sensor | Where-Object { $_.SensorType -eq 'Temperature' }
  if ($sensors) {
    foreach ($sensor in $sensors) {
      Write-Output ('{0}|{1}|{2}' -f $ns, $sensor.Name, $sensor.Value)
    }
    exit 0
  }
}
$zones = Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature
foreach ($zone in $zones) {
  $celsius = ([double]$zone.CurrentTemperature / 10.0) - 273.15
  Write-Output ('{0}|{1}|{2}' -f 'root/WMI', $zone.InstanceName, $celsius)
}
"""


def collect_temperature() -> Dict[str, Any]:
    if sys.platform != "win32":
        return dict(_NOT_AVAILABLE_TEMP, checked_at=now_iso())

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return dict(
            _NOT_AVAILABLE_TEMP,
            reason="PowerShell is unavailable; temperature sensors cannot be queried.",
            checked_at=now_iso(),
        )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _TEMPERATURE_SCRIPT,
            ],
            capture_output=True,
            timeout=12,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(
            _NOT_AVAILABLE_TEMP,
            reason=f"Temperature probe failed: {exc}",
            checked_at=now_iso(),
        )

    output = result.stdout.decode("utf-8", errors="replace")
    sensors: List[Dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) != 3:
            continue
        namespace, name, value_text = parts
        try:
            value = float(value_text.replace(",", "."))
        except ValueError:
            continue
        if not 0.0 < value < 130.0:
            continue
        sensors.append(
            {
                "source": namespace,
                "name": name.strip(),
                "celsius": round(value, 1),
            }
        )

    if not sensors:
        return dict(_NOT_AVAILABLE_TEMP, checked_at=now_iso())

    hottest = max(sensors, key=lambda sensor: sensor["celsius"])
    return {
        "available": True,
        "celsius": hottest["celsius"],
        "source": hottest["source"],
        "sensor": hottest["name"],
        "sensors": sensors[:8],
        "reason": None,
        "checked_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# Processes and unresponsive windows
# ---------------------------------------------------------------------------


def normalize_process_name(value: str) -> str:
    name = (value or "").strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def collect_processes(names: List[str]) -> List[Dict[str, Any]]:
    if not names:
        return []

    targets: Dict[str, str] = {}
    for name in names:
        normalized = normalize_process_name(name)
        if normalized:
            targets[normalized] = name

    matches: Dict[str, List[Dict[str, Any]]] = {key: [] for key in targets}
    for proc in psutil.process_iter(["pid", "name", "exe", "status", "memory_info", "create_time"]):
        try:
            info = proc.info
            process_name = normalize_process_name(info.get("name") or "")
            exe_name = normalize_process_name(os.path.basename(info.get("exe") or ""))
            keys = {key for key in (process_name, exe_name) if key in targets}
            if not keys:
                continue
            memory = info.get("memory_info")
            started = info.get("create_time")
            row = {
                "pid": info.get("pid"),
                "status": info.get("status") or "unknown",
                "memory_mb": round(memory.rss / (1024 * 1024), 1) if memory else 0.0,
                "started_at": datetime.fromtimestamp(started, tz=timezone.utc).isoformat()
                if started
                else None,
            }
            for key in keys:
                matches[key].append(row)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    result: List[Dict[str, Any]] = []
    for key, display_name in targets.items():
        rows = matches.get(key, [])
        result.append(
            {
                "name": display_name,
                "running": bool(rows),
                "instances": len(rows),
                "pids": [row["pid"] for row in rows],
                "memory_mb": round(sum(row["memory_mb"] for row in rows), 1),
                "status": rows[0]["status"] if rows else "not running",
                "started_at": min(
                    (row["started_at"] for row in rows if row["started_at"]),
                    default=None,
                ),
            }
        )
    return result


def _get_window_text(hwnd: int) -> str:
    if not user32:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_process(hwnd: int) -> tuple[int, str]:
    if not user32:
        return 0, "unknown"
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value)
        return int(pid.value), proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return int(pid.value), "unknown"


def collect_hung_windows() -> List[Dict[str, Any]]:
    if not user32 or not hasattr(user32, "IsHungAppWindow"):
        return []

    own_pid = os.getpid()
    items: List[Dict[str, Any]] = []

    def enum_proc(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if not user32.IsHungAppWindow(hwnd):
                return True
            title = _get_window_text(hwnd)
            if not title.strip():
                return True
            pid, process_name = _window_process(hwnd)
            if pid == own_pid:
                return True
            items.append(
                {
                    "handle": int(hwnd),
                    "title": title,
                    "pid": pid,
                    "process_name": process_name,
                }
            )
        except Exception:  # pragma: no cover - defensive enumeration
            return True
        return True

    try:
        user32.EnumWindows(_ENUM_PROC(enum_proc), 0)
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.debug("Window enumeration failed: %s", exc)
    return items


# ---------------------------------------------------------------------------
# Windows Event Log
# ---------------------------------------------------------------------------


def windows_events_available() -> bool:
    return sys.platform == "win32" and shutil.which("wevtutil") is not None


def _decode_wevtutil_output(payload: bytes) -> str:
    if not payload:
        return ""
    if payload.startswith(b"\xff\xfe") or payload.startswith(b"\xfe\xff"):
        return payload.decode("utf-16", errors="replace")
    if payload[:4] in (b"<\x00?\x00", b"\x00<\x00?"):
        return payload.decode("utf-16-le", errors="replace")
    return payload.decode("utf-8", errors="replace")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_event_xml(text: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    cleaned = re.sub(r"<\?xml[^>]*\?>", "", text)
    wrapped = f"<Events>{cleaned}</Events>"
    try:
        root = ElementTree.fromstring(wrapped)
    except ElementTree.ParseError as exc:
        logger.debug("Could not parse Windows Event XML: %s", exc)
        return []

    events: List[Dict[str, Any]] = []
    for element in root:
        if _local_name(element.tag) != "Event":
            continue
        record: Dict[str, Any] = {"data": {}}
        for child in element:
            local = _local_name(child.tag)
            if local == "System":
                for field in child:
                    name = _local_name(field.tag)
                    if name == "Provider":
                        record["provider"] = field.attrib.get("Name")
                    elif name == "TimeCreated":
                        record["time_created"] = field.attrib.get("SystemTime")
                    elif name == "EventRecordID":
                        record["record_id"] = (field.text or "").strip()
                    elif name in ("EventID", "Level", "Channel", "Computer"):
                        record[name.lower()] = (field.text or "").strip()
            elif local == "EventData":
                for field in child:
                    if _local_name(field.tag) != "Data":
                        continue
                    key = field.attrib.get("Name") or f"param{len(record['data']) + 1}"
                    record["data"][key] = (field.text or "").strip()
            elif local == "UserData":
                for field in child.iter():
                    key = _local_name(field.tag)
                    if field.text and field.text.strip():
                        record["data"].setdefault(key, field.text.strip())
        try:
            record["event_id"] = int(record.get("eventid") or 0)
        except ValueError:
            record["event_id"] = 0
        try:
            record["level"] = int(record.get("level") or 0)
        except ValueError:
            record["level"] = 0
        record.pop("eventid", None)
        events.append(record)
    return events


def _run_wevtutil(log_name: str, xpath: str, count: int) -> tuple[List[Dict[str, Any]], Optional[str]]:
    command = [
        "wevtutil",
        "qe",
        log_name,
        f"/q:{xpath}",
        "/rd:true",
        f"/c:{count}",
        "/f:xml",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=20,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], str(exc)
    if result.returncode != 0:
        error = _decode_wevtutil_output(result.stderr).strip()
        return [], error or f"wevtutil exited with {result.returncode}"
    return _parse_event_xml(_decode_wevtutil_output(result.stdout)), None


def read_windows_events(
    lookback_seconds: int,
    max_per_log: int,
) -> Dict[str, Any]:
    if not windows_events_available():
        return {
            "available": False,
            "reason": "Windows Event Log access is only available on Windows with wevtutil.",
            "events": [],
            "errors": [],
        }

    cutoff = time.time() - max(30, lookback_seconds)
    events: List[Dict[str, Any]] = []
    errors: List[str] = []

    for log_name, xpath in (
        ("System", _SYSTEM_EVENT_XPATH),
        ("Application", _APPLICATION_EVENT_XPATH),
    ):
        parsed, error = _run_wevtutil(log_name, xpath, max_per_log)
        if error:
            errors.append(f"{log_name}: {error}")
            continue
        for record in parsed:
            record["channel"] = record.get("channel") or log_name
            record["log"] = log_name
            time_created = record.get("time_created")
            if not time_created:
                continue
            try:
                moment = datetime.fromisoformat(time_created.replace("Z", "+00:00"))
            except ValueError:
                continue
            if moment.timestamp() < cutoff:
                continue
            events.append(record)

    events.sort(key=lambda item: item.get("time_created") or "", reverse=True)
    return {
        "available": True,
        "reason": None,
        "events": events,
        "errors": errors,
        "checked_at": now_iso(),
    }


def event_application_name(record: Dict[str, Any]) -> Optional[str]:
    data = record.get("data") or {}
    for key in ("AppName", "Application", "ApplicationName", "param1", "Image"):
        value = data.get(key)
        if value:
            return os.path.basename(str(value).strip())
    return None


def event_summary(record: Dict[str, Any]) -> str:
    data = record.get("data") or {}
    parts: List[str] = []
    for key, value in list(data.items())[:4]:
        if value:
            parts.append(f"{key}={value}")
    if parts:
        return "; ".join(parts)[:400]
    return f"Provider {record.get('provider') or 'unknown'} reported event {record.get('event_id')}."


def event_dedupe_key(record: Dict[str, Any]) -> str:
    log_name = record.get("log") or record.get("channel") or "log"
    record_id = record.get("record_id")
    if record_id:
        return f"winevent:{log_name}:{record_id}"
    return "winevent:{log}:{provider}:{event}:{time}".format(
        log=log_name,
        provider=record.get("provider") or "unknown",
        event=record.get("event_id") or 0,
        time=record.get("time_created") or "",
    )


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
