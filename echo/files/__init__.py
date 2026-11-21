"""Stage 6 file intelligence: approved-directory indexing and safe actions."""
from echo.files.service import (
    ConfirmationRequired,
    FileIntelligenceError,
    FileIntelligenceService,
    PathNotApproved,
    get_file_service,
    set_file_service,
)

__all__ = [
    "ConfirmationRequired",
    "FileIntelligenceError",
    "FileIntelligenceService",
    "PathNotApproved",
    "get_file_service",
    "set_file_service",
]
