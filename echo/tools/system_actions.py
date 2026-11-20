import os
import subprocess
import webbrowser
from typing import Optional
from pydantic import BaseModel, Field
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry


class EmptyArgs(BaseModel):
    pass


class OpenExplorerArgs(BaseModel):
    path: Optional[str] = Field(default=None, description="Directory path to open in File Explorer")


class OpenBrowserArgs(BaseModel):
    url: str = Field(default="https://google.com", description="Web address to navigate to in the default browser")


async def handle_open_settings(args: EmptyArgs):
    os.system("start ms-settings:")
    return {"launched": "Windows Settings (ms-settings:)", "success": True}


async def handle_open_explorer(args: OpenExplorerArgs):
    if args.path and os.path.exists(args.path):
        subprocess.Popen(["explorer.exe", os.path.abspath(args.path)])
    else:
        subprocess.Popen(["explorer.exe"])
    return {"launched": "File Explorer", "path": args.path, "success": True}


async def handle_open_task_manager(args: EmptyArgs):
    subprocess.Popen(["taskmgr.exe"])
    return {"launched": "Task Manager (taskmgr.exe)", "success": True}


async def handle_open_browser(args: OpenBrowserArgs):
    url = args.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    webbrowser.open(url)
    return {"launched": "Default Web Browser", "url": url, "success": True}


def register_system_action_tools(registry: ToolRegistry):
    registry.register(
        name="system.open_settings",
        description="Open Windows Settings panel",
        category=ToolCategory.SYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_open_settings,
    )
    registry.register(
        name="system.open_explorer",
        description="Open Windows File Explorer at an approved location",
        category=ToolCategory.SYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=OpenExplorerArgs,
        executor=handle_open_explorer,
    )
    registry.register(
        name="system.open_task_manager",
        description="Open Windows Task Manager",
        category=ToolCategory.SYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_open_task_manager,
    )
    registry.register(
        name="system.open_browser",
        description="Open the default web browser to a validated URL",
        category=ToolCategory.SYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=OpenBrowserArgs,
        executor=handle_open_browser,
    )
