"""Content extraction and file categorization.

Text-like formats and Office Open XML documents are handled with the standard
library. PDF and OCR support is optional and reports its absence honestly.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional
from xml.etree import ElementTree

CATEGORY_BY_EXTENSION: Dict[str, str] = {
    **{ext: "document" for ext in (".txt", ".md", ".markdown", ".rtf", ".odt", ".pdf", ".doc", ".docx")},
    **{ext: "spreadsheet" for ext in (".csv", ".tsv", ".xls", ".xlsx", ".ods")},
    **{ext: "presentation" for ext in (".ppt", ".pptx", ".odp")},
    **{
        ext: "code"
        for ext in (
            ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml",
            ".ini", ".cfg", ".css", ".scss", ".html", ".htm", ".xml", ".sql", ".sh",
            ".ps1", ".bat", ".cmd", ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".go",
            ".rs", ".rb", ".php", ".vue", ".svelte", ".ipynb",
        )
    },
    **{ext: "image" for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".ico", ".svg")},
    **{ext: "audio" for ext in (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma")},
    **{ext: "video" for ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv")},
    **{ext: "archive" for ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso")},
    **{ext: "executable" for ext in (".exe", ".msi", ".com", ".dll", ".sys", ".scr", ".lnk", ".url")},
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".log", ".ini", ".cfg", ".toml", ".yaml", ".yml",
    ".json", ".xml", ".html", ".htm", ".css", ".scss", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".sql", ".sh", ".ps1", ".bat", ".cmd", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".java", ".go", ".rs", ".rb", ".php", ".vue", ".svelte",
    ".svg", ".ipynb",
}

# Never indexed or read: credentials, key stores, and secret-bearing names.
SKIP_EXTENSIONS = {
    ".pfx", ".p12", ".pem", ".key", ".kdbx", ".keystore", ".jks", ".ppk",
    ".pfx", ".der", ".crt", ".cer",
}
SKIP_NAMES = {
    ".env", ".env.local", ".env.production", "credentials.json", "secrets.json",
    "id_rsa", "id_ed25519", "id_ecdsa", "wp-config.php",
}
SKIP_DIR_NAMES = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", "target",
    "$recycle.bin", "system volume information",
}

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"(?i)\b(password|passwd|passphrase|secret|api[\s_-]?key|private[\s_-]?key|token)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED]"),
]


def category_for(path: Path) -> str:
    return CATEGORY_BY_EXTENSION.get(path.suffix.lower(), "other")


def should_skip(path: Path) -> Optional[str]:
    name = path.name.lower()
    if name in SKIP_NAMES:
        return "credential or secret file"
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return "credential or key file"
    return None


def redact_content(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def compute_hash(path: Path, max_bytes: int) -> Optional[str]:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _clip(text: str, max_chars: int) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def _element_text(xml_bytes: bytes, tags: set[str]) -> str:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return ""
    parts = []
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag in tags and element.text:
            parts.append(element.text)
    return " ".join(parts)


def _extract_docx(path: Path, max_chars: int) -> tuple[str, str, str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        target = "word/document.xml" if "word/document.xml" in names else None
        if not target:
            return "", "unsupported", "DOCX has no document.xml"
        text = _element_text(archive.read(target), {"t"})
        return _clip(text, max_chars), "indexed", "docx"


def _extract_pptx(path: Path, max_chars: int) -> tuple[str, str, str]:
    with zipfile.ZipFile(path) as archive:
        slides = sorted(
            (n for n in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.search(r"slide(\d+)", n).group(1)),
        )
        chunks = []
        for name in slides:
            text = _element_text(archive.read(name), {"t"})
            if text.strip():
                chunks.append(text)
        return _clip("\n".join(chunks), max_chars), "indexed", "pptx"


def _extract_xlsx(path: Path, max_chars: int) -> tuple[str, str, str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            try:
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root:
                    pieces = [
                        node.text or ""
                        for node in item.iter()
                        if node.tag.split("}")[-1] == "t"
                    ]
                    shared.append("".join(pieces))
            except ElementTree.ParseError:
                shared = []

        chunks = []
        for name in sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError:
                continue
            rows = []
            for row in root.iter():
                if row.tag.split("}")[-1] != "row":
                    continue
                cells = []
                for cell in row:
                    if cell.tag.split("}")[-1] != "c":
                        continue
                    cell_type = cell.attrib.get("t")
                    value = ""
                    for child in cell.iter():
                        tag = child.tag.split("}")[-1]
                        if tag == "v" and child.text:
                            value = child.text
                        elif tag == "t" and child.text:
                            value += child.text
                    if cell_type == "s" and value.isdigit():
                        index = int(value)
                        value = shared[index] if index < len(shared) else value
                    if value:
                        cells.append(value)
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                chunks.append("\n".join(rows))
        return _clip("\n\n".join(chunks), max_chars), "indexed", "xlsx"


def _extract_csv(path: Path, max_chars: int) -> tuple[str, str, str]:
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            rows.append(" | ".join(cell.strip() for cell in row))
            if index >= 2000 or sum(len(r) for r in rows) >= max_chars:
                break
    return _clip("\n".join(rows), max_chars), "indexed", "csv"


def _extract_pdf(path: Path, max_chars: int) -> tuple[str, str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return "", "unsupported", "PDF text extraction requires the optional pypdf package"
    try:
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            return "", "unsupported", "PDF is encrypted"
        chunks = []
        for page in reader.pages[:500]:
            chunks.append(page.extract_text() or "")
            if sum(len(c) for c in chunks) >= max_chars:
                break
        return _clip("\n".join(chunks), max_chars), "indexed", "pypdf"
    except Exception as exc:
        return "", "error", f"PDF extraction failed: {exc}"


def _extract_image(path: Path, max_chars: int, ocr_enabled: bool) -> tuple[str, str, str, Dict[str, Any]]:
    metadata: Dict[str, Any] = {}
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return "", "metadata_only", "Pillow is not installed", metadata
    try:
        with Image.open(path) as image:
            metadata.update(
                {
                    "format": image.format,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                }
            )
            exif = getattr(image, "getexif", lambda: None)()
            if exif:
                for tag, value in list(exif.items())[:20]:
                    metadata[f"exif_{tag}"] = str(value)[:120]
            text = ""
            if ocr_enabled:
                try:
                    import pytesseract  # type: ignore

                    text = pytesseract.image_to_string(image)
                except Exception as exc:
                    metadata["ocr_error"] = str(exc)
    except Exception as exc:
        return "", "error", f"Image metadata failed: {exc}", metadata

    if text.strip():
        return _clip(text, max_chars), "indexed", "pillow+tesseract", metadata
    return "", "metadata_only", "metadata_only", metadata


def extract_text(
    path: Path,
    max_chars: int = 20000,
    ocr_enabled: bool = False,
) -> Dict[str, Any]:
    """Extract searchable text and metadata from a supported file."""
    suffix = path.suffix.lower()
    metadata: Dict[str, Any] = {"suffix": suffix, "category": category_for(path)}
    try:
        if suffix in TEXT_EXTENSIONS:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read(max_chars * 2)
            return {
                "text": _clip(redact_content(text), max_chars),
                "status": "indexed",
                "extractor": "text",
                "metadata": metadata,
            }
        if suffix in (".csv", ".tsv"):
            text, status, extractor = _extract_csv(path, max_chars)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        if suffix == ".docx":
            text, status, extractor = _extract_docx(path, max_chars)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        if suffix == ".xlsx":
            text, status, extractor = _extract_xlsx(path, max_chars)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        if suffix == ".pptx":
            text, status, extractor = _extract_pptx(path, max_chars)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        if suffix == ".pdf":
            text, status, extractor = _extract_pdf(path, max_chars)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        if suffix in CATEGORY_BY_EXTENSION and CATEGORY_BY_EXTENSION[suffix] == "image":
            text, status, extractor, extra = _extract_image(path, max_chars, ocr_enabled)
            metadata.update(extra)
            return {"text": redact_content(text), "status": status, "extractor": extractor, "metadata": metadata}
        return {
            "text": "",
            "status": "unsupported",
            "extractor": "none",
            "metadata": metadata,
        }
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        return {
            "text": "",
            "status": "error",
            "extractor": "none",
            "metadata": metadata,
            "error": str(exc),
        }


def capabilities() -> Dict[str, bool]:
    pdf = False
    try:
        import pypdf  # type: ignore  # noqa: F401

        pdf = True
    except ImportError:
        try:
            import PyPDF2  # type: ignore  # noqa: F401

            pdf = True
        except ImportError:
            pdf = False
    ocr = False
    try:
        import pytesseract  # type: ignore  # noqa: F401

        ocr = True
    except ImportError:
        ocr = False
    return {
        "text": True,
        "csv": True,
        "docx": True,
        "xlsx": True,
        "pptx": True,
        "pdf": pdf,
        "image_metadata": True,
        "ocr": ocr,
    }
