import pyperclip
from pydantic import BaseModel, Field
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry


class EmptyArgs(BaseModel):
    pass


class WriteClipboardArgs(BaseModel):
    text: str = Field(description="Text string to write to Windows clipboard")


async def handle_read_clipboard(args: EmptyArgs):
    try:
        content = pyperclip.paste()
        return {
            "text": content,
            "length": len(content),
        }
    except Exception as ex:
        return {"text": "", "error": str(ex)}


async def handle_write_clipboard(args: WriteClipboardArgs):
    try:
        pyperclip.copy(args.text)
        return {"success": True, "copied_length": len(args.text)}
    except Exception as ex:
        return {"success": False, "error": str(ex)}


def register_clipboard_tools(registry: ToolRegistry):
    registry.register(
        name="clipboard.read",
        description="Read current text content from the Windows clipboard",
        category=ToolCategory.CLIPBOARD,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=EmptyArgs,
        executor=handle_read_clipboard,
    )
    registry.register(
        name="clipboard.write",
        description="Write text directly to the Windows clipboard",
        category=ToolCategory.CLIPBOARD,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=WriteClipboardArgs,
        executor=handle_write_clipboard,
    )
