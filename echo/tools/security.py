import os
from pathlib import Path
from typing import List, Optional


# Hard-blocked system & security paths on Windows
BLOCKED_PATH_PATTERNS = [
    r"windows\system32\config",
    r"system volume information",
    r"$recycle.bin",
    r"windows\repair",
    r"appdata\local\microsoft\credentials",
    r"appdata\roaming\microsoft\credentials",
    r"appdata\local\microsoft\vault",
    r"\.ssh",
    r"\.aws",
    r"\.gnupg",
    r"\.azure",
    r"\.env",
]

# Prohibited file extensions for direct execution or script modification
RESTRICTED_EXECUTABLE_EXTENSIONS = [
    ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf", ".hta", ".scr", ".pif"
]

# Safe system applications permitted for direct launch
APPROVED_APPLICATIONS = {
    "notepad": r"C:\Windows\System32\notepad.exe",
    "calculator": r"calc.exe",
    "paint": r"C:\Windows\System32\mspaint.exe",
    "explorer": r"C:\Windows\explorer.exe",
    "taskmgr": r"C:\Windows\System32\taskmgr.exe",
    "cmd": r"C:\Windows\System32\cmd.exe",
}


def is_path_safe(path: Path | str) -> tuple[bool, str]:
    """Inspect path for traversal attempts, forbidden system files, or credential hives."""
    try:
        resolved = Path(path).resolve()
        path_str = str(resolved).lower()

        # Check for blocked path patterns
        for pattern in BLOCKED_PATH_PATTERNS:
            if pattern in path_str:
                return False, f"Access to restricted system or credential path is blocked: '{pattern}'"

        return True, ""
    except Exception as ex:
        return False, f"Path resolution error: {str(ex)}"


def validate_path(
    path: Path | str,
    must_exist: bool = True,
    allow_create: bool = False,
) -> Path:
    """Validate path and raise PermissionError or FileNotFoundError if unsafe."""
    safe, reason = is_path_safe(path)
    if not safe:
        raise PermissionError(reason)

    resolved = Path(path).resolve()
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"File or directory does not exist: '{resolved}'")

    if not allow_create and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: '{resolved}'")

    return resolved
