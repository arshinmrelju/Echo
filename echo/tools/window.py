import ctypes
from ctypes import wintypes
import sys
from typing import List, Optional
from pydantic import BaseModel, Field
import psutil
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Win32 Constants
SW_HIDE = 0
SW_MAXIMIZE = 3
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9
WM_CLOSE = 0x0010


# Schemas
class EmptyArgs(BaseModel):
    pass


class WindowActionArgs(BaseModel):
    handle: int = Field(description="HWND handle of the target window")


class WindowTitleArgs(BaseModel):
    title_query: str = Field(description="Title substring to identify the window")


# Helpers
def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    return ""


def _get_window_process(hwnd: int) -> tuple[int, str]:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value)
        return pid.value, proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return pid.value, "unknown"


# Handlers
async def handle_list_windows(args: EmptyArgs):
    if not user32:
        return {"windows": [], "count": 0}

    windows = []

    def enum_proc(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            title = _get_window_text(hwnd)
            if title.strip():
                pid, proc_name = _get_window_process(hwnd)
                is_min = bool(user32.IsIconic(hwnd))
                is_max = bool(user32.IsZoomed(hwnd))
                windows.append({
                    "handle": hwnd,
                    "title": title,
                    "process_name": proc_name,
                    "pid": pid,
                    "is_minimized": is_min,
                    "is_maximized": is_max,
                })
        return True

    ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(ENUMPROC(enum_proc), 0)
    return {"windows": windows, "count": len(windows)}


async def handle_get_active_window(args: EmptyArgs):
    if not user32:
        return {"handle": 0, "title": "Unsupported OS", "process_name": "none"}

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"handle": 0, "title": "None", "process_name": "none"}

    title = _get_window_text(hwnd)
    pid, proc_name = _get_window_process(hwnd)
    return {
        "handle": hwnd,
        "title": title,
        "pid": pid,
        "process_name": proc_name,
    }


async def handle_switch_window(args: WindowActionArgs):
    if not user32:
        return {"success": False}
    user32.ShowWindow(args.handle, SW_RESTORE)
    res = user32.SetForegroundWindow(args.handle)
    return {"handle": args.handle, "activated": bool(res)}


async def handle_minimize_window(args: WindowActionArgs):
    if not user32:
        return {"success": False}
    res = user32.ShowWindow(args.handle, SW_MINIMIZE)
    return {"handle": args.handle, "minimized": True}


async def handle_maximize_window(args: WindowActionArgs):
    if not user32:
        return {"success": False}
    res = user32.ShowWindow(args.handle, SW_MAXIMIZE)
    return {"handle": args.handle, "maximized": True}


async def handle_restore_window(args: WindowActionArgs):
    if not user32:
        return {"success": False}
    res = user32.ShowWindow(args.handle, SW_RESTORE)
    return {"handle": args.handle, "restored": True}


async def handle_close_window(args: WindowActionArgs):
    if not user32:
        return {"success": False}
    title = _get_window_text(args.handle)
    res = user32.PostMessageW(args.handle, WM_CLOSE, 0, 0)
    return {"handle": args.handle, "title": title, "closed": bool(res)}


def register_window_tools(registry: ToolRegistry):
    registry.register(
        name="window.list",
        description="List all visible top-level Windows applications and titles",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_list_windows,
    )
    registry.register(
        name="window.get_active",
        description="Get current foreground window title, handle, and process",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_get_active_window,
    )
    registry.register(
        name="window.switch",
        description="Bring a target window to foreground focus by handle",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=WindowActionArgs,
        executor=handle_switch_window,
    )
    registry.register(
        name="window.minimize",
        description="Minimize target window",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=WindowActionArgs,
        executor=handle_minimize_window,
    )
    registry.register(
        name="window.maximize",
        description="Maximize target window",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=WindowActionArgs,
        executor=handle_maximize_window,
    )
    registry.register(
        name="window.restore",
        description="Restore a minimized or maximized window",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=WindowActionArgs,
        executor=handle_restore_window,
    )
    registry.register(
        name="window.close",
        description="Close a window safely (Requires Approval)",
        category=ToolCategory.WINDOW,
        permission_level=PermissionLevel.APPROVAL_REQUIRED,
        input_schema=WindowActionArgs,
        executor=handle_close_window,
    )
