import asyncio
from pathlib import Path
import pytest
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.bootstrap import initialize_all_tools
from echo.tools.permissions import get_permission_manager
from echo.tools.registry import ToolRegistry, get_tool_registry
from echo.tools.security import is_path_safe, validate_path


@pytest.fixture
def registry(temp_db):
    reg = ToolRegistry(db=temp_db)
    initialize_all_tools(reg)
    return reg


# 1. Registration & Listing Tests
def test_tool_registry_registration(registry: ToolRegistry):
    tools = registry.list_tools()
    assert len(tools) >= 20
    names = [t["name"] for t in tools]
    assert "screen.capture_desktop" in names
    assert "window.list" in names
    assert "mouse.move" in names
    assert "keyboard.type_text" in names
    assert "application.list" in names
    assert "filesystem.read_file" in names
    assert "clipboard.read" in names
    assert "system.open_settings" in names


# 2. Security & Path Traversal Tests
def test_security_blocked_paths():
    safe, reason = is_path_safe(r"C:\Windows\System32\config\SAM")
    assert safe is False
    assert "blocked" in reason

    safe, reason = is_path_safe(r"C:\Users\User\AppData\Local\Microsoft\Credentials")
    assert safe is False

    safe, reason = is_path_safe(r"C:\Users\User\.ssh\id_rsa")
    assert safe is False

    safe, reason = is_path_safe(r"D:\Echo\data\.env")
    assert safe is False

    safe, _ = is_path_safe(r"D:\Echo\README.md")
    assert safe is True


def test_security_validate_path(temp_dir: Path):
    test_file = temp_dir / "sample.txt"
    test_file.write_text("Hello ECHO")

    validated = validate_path(test_file, must_exist=True)
    assert validated.exists()

    with pytest.raises(PermissionError):
        validate_path(r"C:\Windows\System32\config\SYSTEM")

    with pytest.raises(FileNotFoundError):
        validate_path(temp_dir / "nonexistent_file.txt", must_exist=True)


# 3. Individual Tool Execution Tests
@pytest.mark.asyncio
async def test_screen_capture_desktop(registry: ToolRegistry):
    result = await registry.execute("screen.capture_desktop", {})
    assert result.success is True
    assert "file_path" in result.data
    assert Path(result.data["file_path"]).exists()


@pytest.mark.asyncio
async def test_window_tools(registry: ToolRegistry):
    res_list = await registry.execute("window.list", {})
    assert res_list.success is True
    assert "windows" in res_list.data

    res_active = await registry.execute("window.get_active", {})
    assert res_active.success is True
    assert "title" in res_active.data


@pytest.mark.asyncio
async def test_mouse_tools(registry: ToolRegistry):
    res_move = await registry.execute("mouse.move", {"x": 100, "y": 100, "duration": 0.0})
    assert res_move.success is True
    assert res_move.data["x"] == 100
    assert res_move.data["y"] == 100

    res_scroll = await registry.execute("mouse.scroll", {"clicks": 2})
    assert res_scroll.success is True


@pytest.mark.asyncio
async def test_keyboard_tools(registry: ToolRegistry):
    res_press = await registry.execute("keyboard.press_key", {"key": "shift"})
    assert res_press.success is True
    assert res_press.data["pressed"] is True

    res_hotkey = await registry.execute("keyboard.hotkey", {"keys": ["shift", "shift"]})
    assert res_hotkey.success is True


@pytest.mark.asyncio
async def test_clipboard_tools(registry: ToolRegistry):
    res_write = await registry.execute("clipboard.write", {"text": "ECHO test clipboard"})
    assert res_write.success is True

    res_read = await registry.execute("clipboard.read", {})
    assert res_read.success is True
    assert res_read.data["text"] == "ECHO test clipboard"


@pytest.mark.asyncio
async def test_filesystem_tools(registry: ToolRegistry, temp_dir: Path):
    # Create folder
    new_dir = temp_dir / "test_folder"
    res_mkdir = await registry.execute("filesystem.create_folder", {"path": str(new_dir)})
    assert res_mkdir.success is True
    assert new_dir.exists()

    # List folder
    res_list = await registry.execute("filesystem.list_dir", {"path": str(temp_dir)})
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Write & read file
    sample = new_dir / "note.txt"
    sample.write_text("Secret agent briefing.")
    res_read = await registry.execute("filesystem.read_file", {"path": str(sample)})
    assert res_read.success is True
    assert "Secret agent briefing." in res_read.data["content"]

    # Search file
    res_search = await registry.execute(
        "filesystem.search",
        {"directory": str(temp_dir), "pattern": "*.txt"},
    )
    assert res_search.success is True
    assert res_search.data["count"] >= 1

    # Copy file
    dest = new_dir / "note_copy.txt"
    res_copy = await registry.execute(
        "filesystem.copy_file",
        {"source_path": str(sample), "destination_path": str(dest)},
    )
    assert res_copy.success is True
    assert dest.exists()


# 4. Invalid Arguments Handling
@pytest.mark.asyncio
async def test_invalid_arguments(registry: ToolRegistry):
    # Missing required argument
    res = await registry.execute("clipboard.write", {})
    assert res.success is False
    assert "validation error" in res.error.lower()

    # Out of range coordinates
    res = await registry.execute("mouse.move", {"x": -50, "y": 100})
    assert res.success is False
    assert "validation error" in res.error.lower()


# 5. Permission Approval Flow
@pytest.mark.asyncio
async def test_approval_gate_flow(registry: ToolRegistry, temp_dir: Path):
    src = temp_dir / "move_me.txt"
    src.write_text("move content")
    dest = temp_dir / "moved.txt"

    # filesystem.move_file is APPROVAL_REQUIRED
    res = await registry.execute(
        "filesystem.move_file",
        {"source_path": str(src), "destination_path": str(dest)},
    )
    assert res.success is False
    assert res.requires_approval is True
    assert res.approval_request_id is not None

    req_id = res.approval_request_id
    pm = get_permission_manager()

    # Deny first
    pm.resolve_request(req_id, approved=False)
    res_denied = await registry.execute(
        "filesystem.move_file",
        {"source_path": str(src), "destination_path": str(dest)},
        approval_id=req_id,
    )
    assert res_denied.success is False
    assert "not approved" in res_denied.error

    # Now create new request and approve
    res_new = await registry.execute(
        "filesystem.move_file",
        {"source_path": str(src), "destination_path": str(dest)},
    )
    req_new_id = res_new.approval_request_id
    pm.resolve_request(req_new_id, approved=True)

    res_approved = await registry.execute(
        "filesystem.move_file",
        {"source_path": str(src), "destination_path": str(dest)},
        approval_id=req_new_id,
    )
    assert res_approved.success is True
    assert dest.exists()


# 6. Timeout Handling
@pytest.mark.asyncio
async def test_tool_timeout(registry: ToolRegistry):
    from pydantic import BaseModel

    class SlowArgs(BaseModel):
        delay: float

    async def slow_fn(args: SlowArgs):
        await asyncio.sleep(args.delay)
        return "done"

    registry.register(
        name="test.slow",
        description="Slow test tool",
        category=ToolCategory.SYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=SlowArgs,
        executor=slow_fn,
        timeout_seconds=0.1,
    )

    res = await registry.execute("test.slow", {"delay": 0.5})
    assert res.success is False
    assert "timed out" in res.error
