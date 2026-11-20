from pathlib import Path
import shutil
from typing import List, Optional
from pydantic import BaseModel, Field
from echo.tools.base import PermissionLevel, ToolCategory
from echo.tools.registry import ToolRegistry
from echo.tools.security import validate_path


# Schemas
class ListDirArgs(BaseModel):
    path: str = Field(default=".", description="Directory path to inspect")


class SearchFilesArgs(BaseModel):
    directory: str = Field(default=".", description="Root directory to search inside")
    pattern: str = Field(description="Search pattern or extension (e.g. *.txt, report*)")
    max_results: int = Field(default=20, ge=1, le=100)


class ReadFileArgs(BaseModel):
    path: str = Field(description="Path of document to read")
    max_chars: int = Field(default=10000, description="Max characters to read")


class CreateFolderArgs(BaseModel):
    path: str = Field(description="Directory path to create")


class RenameFileArgs(BaseModel):
    source_path: str = Field(description="Existing file path")
    new_name: str = Field(description="New file name")


class MoveFileArgs(BaseModel):
    source_path: str = Field(description="Source file path")
    destination_path: str = Field(description="Destination file or directory path")


class CopyFileArgs(BaseModel):
    source_path: str = Field(description="Source file path")
    destination_path: str = Field(description="Target destination file path")


# Handlers
async def handle_list_dir(args: ListDirArgs):
    target = validate_path(args.path, must_exist=True)
    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: '{target}'")

    items = []
    for entry in target.iterdir():
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if entry.is_file() else None,
                "modified": stat.st_mtime,
            })
        except OSError:
            continue
    return {"path": str(target), "entries": items, "count": len(items)}


async def handle_search_files(args: SearchFilesArgs):
    root = validate_path(args.directory, must_exist=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: '{root}'")

    matches = []
    for match in root.rglob(args.pattern):
        if len(matches) >= args.max_results:
            break
        try:
            matches.append({
                "path": str(match),
                "name": match.name,
                "is_dir": match.is_dir(),
                "size_bytes": match.stat().st_size if match.is_file() else None,
            })
        except OSError:
            continue
    return {"query_pattern": args.pattern, "matches": matches, "count": len(matches)}


async def handle_read_file(args: ReadFileArgs):
    file_path = validate_path(args.path, must_exist=True)
    if not file_path.is_file():
        raise IsADirectoryError(f"Path is a directory, not a file: '{file_path}'")

    # Read text content safely
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(args.max_chars)
        return {
            "path": str(file_path),
            "content": content,
            "length": len(content),
            "truncated": len(content) >= args.max_chars,
        }
    except Exception as ex:
        raise IOError(f"Could not read file: {str(ex)}")


async def handle_create_folder(args: CreateFolderArgs):
    target = validate_path(args.path, must_exist=False, allow_create=True)
    target.mkdir(parents=True, exist_ok=True)
    return {"created": str(target), "success": True}


async def handle_rename_file(args: RenameFileArgs):
    source = validate_path(args.source_path, must_exist=True)
    new_target = source.parent / args.new_name
    validate_path(new_target, must_exist=False, allow_create=True)
    source.rename(new_target)
    return {"old_path": str(source), "new_path": str(new_target)}


async def handle_move_file(args: MoveFileArgs):
    src = validate_path(args.source_path, must_exist=True)
    dest = validate_path(args.destination_path, must_exist=False, allow_create=True)
    shutil.move(str(src), str(dest))
    return {"source": str(src), "destination": str(dest)}


async def handle_copy_file(args: CopyFileArgs):
    src = validate_path(args.source_path, must_exist=True)
    dest = validate_path(args.destination_path, must_exist=False, allow_create=True)
    shutil.copy2(str(src), str(dest))
    return {"source": str(src), "destination": str(dest)}


def register_filesystem_tools(registry: ToolRegistry):
    registry.register(
        name="filesystem.list_dir",
        description="List files and directories in a given folder with metadata",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ListDirArgs,
        executor=handle_list_dir,
    )
    registry.register(
        name="filesystem.search",
        description="Search for files by filename pattern within an authorized directory",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=SearchFilesArgs,
        executor=handle_search_files,
    )
    registry.register(
        name="filesystem.read_file",
        description="Read text and document contents from safe filesystem locations",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=ReadFileArgs,
        executor=handle_read_file,
    )
    registry.register(
        name="filesystem.create_folder",
        description="Create a new folder safely",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=CreateFolderArgs,
        executor=handle_create_folder,
    )
    registry.register(
        name="filesystem.rename_file",
        description="Rename a file within an approved location",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=RenameFileArgs,
        executor=handle_rename_file,
    )
    registry.register(
        name="filesystem.move_file",
        description="Move a file from source to destination path (Requires Approval)",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.APPROVAL_REQUIRED,
        input_schema=MoveFileArgs,
        executor=handle_move_file,
    )
    registry.register(
        name="filesystem.copy_file",
        description="Copy a file to another permitted directory",
        category=ToolCategory.FILESYSTEM,
        permission_level=PermissionLevel.AUTOMATIC,
        input_schema=CopyFileArgs,
        executor=handle_copy_file,
    )
