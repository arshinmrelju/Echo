import time
from typing import List
from pydantic import BaseModel, Field
import pyautogui
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry

# Disable failsafe to allow typing and key events when mouse is idle in corner
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02


class TypeTextArgs(BaseModel):
    text: str = Field(description="Text string to type")
    interval: float = Field(default=0.01, ge=0.0, le=0.5, description="Interval in seconds between characters")


class PressKeyArgs(BaseModel):
    key: str = Field(description="Name of key to press (e.g. enter, esc, tab, backspace, space, f5)")


class HotkeyArgs(BaseModel):
    keys: List[str] = Field(description="List of keys to trigger simultaneously (e.g. ['ctrl', 'c'], ['win', 'r'], ['alt', 'tab'])")


async def handle_type_text(args: TypeTextArgs):
    try:
        pyautogui.write(args.text, interval=args.interval)
        return {"typed_chars": len(args.text)}
    except Exception as ex:
        return {"typed_chars": 0, "error": str(ex)}


async def handle_press_key(args: PressKeyArgs):
    try:
        key_name = args.key.lower().strip()
        pyautogui.press(key_name)
        return {"key": key_name, "pressed": True}
    except Exception as ex:
        return {"key": args.key, "pressed": False, "error": str(ex)}


async def handle_hotkey(args: HotkeyArgs):
    try:
        clean_keys = [k.lower().strip() for k in args.keys]
        pyautogui.hotkey(*clean_keys)
        return {"hotkey": "+".join(clean_keys), "triggered": True}
    except Exception as ex:
        return {"hotkey": "+".join(args.keys), "triggered": False, "error": str(ex)}


def register_keyboard_tools(registry: ToolRegistry):
    registry.register(
        name="keyboard.type_text",
        description="Type text through simulated keyboard input into active window",
        category=ToolCategory.KEYBOARD,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=TypeTextArgs,
        executor=handle_type_text,
    )
    registry.register(
        name="keyboard.press_key",
        description="Press a specific single keyboard key (e.g. enter, esc, tab)",
        category=ToolCategory.KEYBOARD,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=PressKeyArgs,
        executor=handle_press_key,
    )
    registry.register(
        name="keyboard.hotkey",
        description="Execute a key combination (e.g. ctrl+c, alt+tab, win+r)",
        category=ToolCategory.KEYBOARD,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=HotkeyArgs,
        executor=handle_hotkey,
    )
