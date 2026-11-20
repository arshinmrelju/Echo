from echo.tools.applications import register_application_tools
from echo.tools.clipboard import register_clipboard_tools
from echo.tools.filesystem import register_filesystem_tools
from echo.tools.keyboard import register_keyboard_tools
from echo.tools.mouse import register_mouse_tools
from echo.tools.registry import ToolRegistry, get_tool_registry
from echo.tools.screen import register_screen_tools
from echo.tools.system_actions import register_system_action_tools
from echo.tools.window import register_window_tools


def initialize_all_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    reg = registry or get_tool_registry()
    register_screen_tools(reg)
    register_window_tools(reg)
    register_mouse_tools(reg)
    register_keyboard_tools(reg)
    register_application_tools(reg)
    register_filesystem_tools(reg)
    register_clipboard_tools(reg)
    register_system_action_tools(reg)
    return reg
