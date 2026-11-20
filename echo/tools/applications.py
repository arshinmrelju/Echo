import os
from pathlib import Path
import subprocess
from typing import List, Optional
from pydantic import BaseModel, Field
import psutil
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry
from echo.tools.security import APPROVED_APPLICATIONS, RESTRICTED_EXECUTABLE_EXTENSIONS, validate_path


class EmptyArgs(BaseModel):
    pass


class LaunchAppArgs(BaseModel):
    app_name_or_path: str = Field(description="Approved application name (e.g. notepad, calculator, paint) or full executable path")


class CloseAppArgs(BaseModel):
    process_name: Optional[str] = Field(default=None, description="Process executable name (e.g. notepad.exe)")
    pid: Optional[int] = Field(default=None, description="Process ID to terminate")


async def handle_list_apps(args: EmptyArgs):
    # Return available approved applications plus running GUI processes
    running_apps = []
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            info = proc.info
            name = info["name"]
            if name.endswith(".exe") and info["status"] == psutil.STATUS_RUNNING:
                running_apps.append({"pid": info["pid"], "name": name})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {
        "approved_shortcuts": list(APPROVED_APPLICATIONS.keys()),
        "running_processes": running_apps[:50],
    }


async def handle_launch_app(args: LaunchAppArgs):
    target = args.app_name_or_path.strip().lower()

    # 1. Check approved shortcuts
    if target in APPROVED_APPLICATIONS:
        exec_path = APPROVED_APPLICATIONS[target]
        proc = subprocess.Popen([exec_path])
        return {"app": target, "pid": proc.pid, "executable": exec_path, "success": True}

    # 2. Check direct path
    path = Path(args.app_name_or_path)
    if path.suffix.lower() in RESTRICTED_EXECUTABLE_EXTENSIONS:
        raise PermissionError(f"Direct execution of script files ({path.suffix}) is prohibited by security policy.")

    valid_path = validate_path(path, must_exist=True)
    if not str(valid_path).lower().endswith(".exe"):
        raise PermissionError("Only verified binary executables (.exe) may be launched.")

    proc = subprocess.Popen([str(valid_path)])
    return {"app": valid_path.name, "pid": proc.pid, "executable": str(valid_path), "success": True}


async def handle_close_app(args: CloseAppArgs):
    closed = []
    if args.pid:
        try:
            p = psutil.Process(args.pid)
            name = p.name()
            p.terminate()
            closed.append({"pid": args.pid, "name": name})
        except psutil.NoSuchProcess:
            raise ProcessLookupError(f"No process with PID {args.pid} found.")
    elif args.process_name:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"].lower() == args.process_name.lower():
                    p.terminate()
                    closed.append({"pid": p.info["pid"], "name": p.info["name"]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not closed:
        return {"closed": [], "success": False, "message": "No matching processes were terminated."}

    return {"closed": closed, "success": True}


def register_application_tools(registry: ToolRegistry):
    registry.register(
        name="application.list",
        description="List approved applications and currently running desktop processes",
        category=ToolCategory.APPLICATION,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_list_apps,
    )
    registry.register(
        name="application.launch",
        description="Launch an approved Windows application (notepad, calculator, explorer, etc.)",
        category=ToolCategory.APPLICATION,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=LaunchAppArgs,
        executor=handle_launch_app,
    )
    registry.register(
        name="application.close",
        description="Safely close or terminate an application by name or PID (Requires Approval)",
        category=ToolCategory.APPLICATION,
        permission_level=PermissionLevel.APPROVAL_REQUIRED,
        input_schema=CloseAppArgs,
        executor=handle_close_app,
    )
