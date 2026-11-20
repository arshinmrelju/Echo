import ctypes
from ctypes import wintypes
import sys
import time
from typing import Literal, Optional
from pydantic import BaseModel, Field
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Win32 Mouse Event Flags
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800


class MoveMouseArgs(BaseModel):
    x: int = Field(ge=0, le=7680, description="Target X coordinate on screen")
    y: int = Field(ge=0, le=4320, description="Target Y coordinate on screen")
    duration: float = Field(default=0.0, ge=0.0, le=3.0, description="Movement transition seconds")


class ClickMouseArgs(BaseModel):
    button: Literal["left", "right", "middle"] = Field(default="left")
    x: Optional[int] = Field(default=None, description="Optional X coordinate; if null clicks current position")
    y: Optional[int] = Field(default=None, description="Optional Y coordinate; if null clicks current position")
    clicks: int = Field(default=1, ge=1, le=3)


class ScrollMouseArgs(BaseModel):
    clicks: int = Field(description="Number of scroll steps (positive for up, negative for down)")


def _get_cursor_pos() -> tuple[int, int]:
    if not user32:
        return 0, 0
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


async def handle_move_mouse(args: MoveMouseArgs):
    if user32:
        user32.SetCursorPos(args.x, args.y)
    return {"x": args.x, "y": args.y}


async def handle_click_mouse(args: ClickMouseArgs):
    if not user32:
        return {"button": args.button, "x": 0, "y": 0, "clicks": args.clicks}

    if args.x is not None and args.y is not None:
        user32.SetCursorPos(args.x, args.y)
        cx, cy = args.x, args.y
    else:
        cx, cy = _get_cursor_pos()

    down_flag = MOUSEEVENTF_LEFTDOWN
    up_flag = MOUSEEVENTF_LEFTUP
    if args.button == "right":
        down_flag = MOUSEEVENTF_RIGHTDOWN
        up_flag = MOUSEEVENTF_RIGHTUP
    elif args.button == "middle":
        down_flag = MOUSEEVENTF_MIDDLEDOWN
        up_flag = MOUSEEVENTF_MIDDLEUP

    for _ in range(args.clicks):
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        time.sleep(0.01)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        time.sleep(0.02)

    return {"button": args.button, "x": cx, "y": cy, "clicks": args.clicks}


async def handle_double_click(args: ClickMouseArgs):
    args.clicks = 2
    return await handle_click_mouse(args)


async def handle_right_click(args: ClickMouseArgs):
    args.button = "right"
    return await handle_click_mouse(args)


async def handle_scroll_mouse(args: ScrollMouseArgs):
    if user32:
        # Wheel delta is typically 120 per click
        wheel_delta = args.clicks * 120
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
    return {"scroll_clicks": args.clicks}


def register_mouse_tools(registry: ToolRegistry):
    registry.register(
        name="mouse.move",
        description="Move mouse cursor to specific screen coordinates",
        category=ToolCategory.MOUSE,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=MoveMouseArgs,
        executor=handle_move_mouse,
    )
    registry.register(
        name="mouse.click",
        description="Click mouse button at current position or coordinates",
        category=ToolCategory.MOUSE,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ClickMouseArgs,
        executor=handle_click_mouse,
    )
    registry.register(
        name="mouse.double_click",
        description="Double click mouse button at specified position",
        category=ToolCategory.MOUSE,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ClickMouseArgs,
        executor=handle_double_click,
    )
    registry.register(
        name="mouse.right_click",
        description="Right click mouse button at specified position",
        category=ToolCategory.MOUSE,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ClickMouseArgs,
        executor=handle_right_click,
    )
    registry.register(
        name="mouse.scroll",
        description="Scroll mouse wheel up (positive) or down (negative)",
        category=ToolCategory.MOUSE,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ScrollMouseArgs,
        executor=handle_scroll_mouse,
    )
