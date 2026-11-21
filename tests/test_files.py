from pathlib import Path

import pytest

from echo.files.service import (
    ConfirmationRequired,
    FileIntelligenceError,
    FileIntelligenceService,
    PathNotApproved,
)


@pytest.fixture
def service(temp_db):
    return FileIntelligenceService(db=temp_db)


@pytest.fixture
def docs(temp_dir, service):
    root = temp_dir / "docs"
    root.mkdir()
    (root / "apollo-notes.txt").write_text(
        "Apollo launch checklist\nDeliver the memory explorer.", encoding="utf-8"
    )
    (root / "budget.csv").write_text(
        "item,amount\nservers,120\nlicenses,40\n", encoding="utf-8"
    )
    (root / "readme.md").write_text("# ECHO\nLocal file intelligence.", encoding="utf-8")
    service.add_directory(str(root), "Docs", True)
    return root


def test_search_and_actions_require_approved_directory(service, docs, temp_dir):
    outside = temp_dir / "outside.txt"
    outside.write_text("not approved", encoding="utf-8")

    with pytest.raises(PathNotApproved):
        service.details(str(outside))
    with pytest.raises(PathNotApproved):
        service.rename(str(outside), "renamed.txt")
    with pytest.raises(PathNotApproved):
        service.copy(str(docs / "apollo-notes.txt"), str(temp_dir / "elsewhere.txt"))

    # No approved directories means indexing is refused.
    service.store.remove_directory(service.store.list_directories()[0]["id"])
    with pytest.raises(FileIntelligenceError):
        service.index_directory()


def test_index_and_structured_content_search(service, docs):
    result = service.index_directory()
    assert result["indexed"] == 3
    assert result["errors"] == 0

    by_content = service.search(query="Apollo")
    assert by_content["total"] == 1
    assert by_content["results"][0]["name"] == "apollo-notes.txt"
    assert "Apollo" in (by_content["results"][0]["snippet"] or "")

    by_name = service.search(query="readme")
    assert [row["name"] for row in by_name["results"]] == ["readme.md"]

    by_extension = service.search(extension="csv")
    assert [row["name"] for row in by_extension["results"]] == ["budget.csv"]

    by_category = service.search(category="document")
    assert {row["name"] for row in by_category["results"]} == {"apollo-notes.txt", "readme.md"}

    stats = service.stats()
    assert stats["total_files"] == 3
    assert stats["total_bytes"] > 0
    assert stats["last_indexed_at"]
    assert any(entry["category"] == "spreadsheet" for entry in stats["by_category"])


def test_duplicate_detection_and_quarantine_never_deletes(service, docs):
    (docs / "copy-a.txt").write_text("identical content", encoding="utf-8")
    (docs / "copy-b.txt").write_text("identical content", encoding="utf-8")
    service.index_directory()

    groups = service.store.duplicate_groups()
    assert len(groups) == 1
    assert groups[0]["count"] == 2

    plan = service.quarantine_duplicates(str(docs), dry_run=True)
    assert plan["planned"] == 1

    with pytest.raises(ConfirmationRequired):
        service.quarantine_duplicates(str(docs), confirm=False, dry_run=False)

    result = service.quarantine_duplicates(str(docs), confirm=True, dry_run=False)
    assert result["moved"] == 1

    originals = [path for path in docs.glob("copy-*.txt")]
    assert len(originals) == 1  # exactly one copy stays in place
    quarantined = list((docs / "_ECHO_DUPLICATES").rglob("copy-*.txt"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "identical content"


def test_organize_requires_confirmation_and_keeps_files(service, docs):
    service.update_settings({"bulk_confirm_threshold": 2})
    for index in range(3):
        (docs / f"extra-{index}.txt").write_text(f"extra {index}", encoding="utf-8")

    plan = service.organize(str(docs), dry_run=True)
    assert plan["planned"] >= 5
    assert plan["threshold"] == 2

    with pytest.raises(ConfirmationRequired):
        service.organize(str(docs), dry_run=False, confirm=False)

    result = service.organize(str(docs), dry_run=False, confirm=True)
    assert result["moved"] == plan["planned"]
    assert (docs / "Documents").is_dir()
    assert (docs / "Spreadsheets").is_dir()

    # Nothing vanished: every planned source now exists at its target.
    for item in plan["plan"]:
        assert Path(item["target"]).exists()


def test_bulk_rename_requires_confirmation(service, docs):
    (docs / "draft-one.txt").write_text("a", encoding="utf-8")
    (docs / "draft-two.txt").write_text("b", encoding="utf-8")

    plan = service.bulk_rename(str(docs), "draft", "final", dry_run=True)
    assert plan["planned"] == 2

    with pytest.raises(ConfirmationRequired):
        service.bulk_rename(str(docs), "draft", "final", dry_run=False, confirm=False)

    result = service.bulk_rename(str(docs), "draft", "final", dry_run=False, confirm=True)
    assert result["renamed"] == 2
    assert (docs / "final-one.txt").exists()
    assert (docs / "final-two.txt").exists()


def test_credential_files_are_skipped_and_search_text_is_redacted(service, docs):
    (docs / ".env").write_text("API_KEY=sk-abcdefghijklmnop", encoding="utf-8")
    (docs / "credentials.json").write_text('{"password": "hunter2"}', encoding="utf-8")
    (docs / "server-notes.txt").write_text(
        "Server password=SuperSecret123 and launch sequence bravo.", encoding="utf-8"
    )

    service.index_directory()
    names = {row["name"] for row in service.search(limit=100)["results"]}
    assert ".env" not in names
    assert "credentials.json" not in names

    assert service.search(query="SuperSecret123")["total"] == 0
    assert service.search(query="Apollo")["total"] == 1

    details = service.details(str(docs / "server-notes.txt"))
    assert "SuperSecret123" not in (details.get("preview") or "")


def test_removing_directory_never_touches_disk(service, docs):
    service.index_directory()
    before = sorted(path.name for path in docs.iterdir())

    directory = service.store.list_directories()[0]
    assert service.remove_directory(directory["id"]) is True

    assert sorted(path.name for path in docs.iterdir()) == before
    assert service.stats()["total_files"] == 0
    assert not service.store.list_directories()


def test_executables_are_not_opened(service, docs):
    executable = docs / "setup.exe"
    executable.write_bytes(b"MZ")
    with pytest.raises(FileIntelligenceError):
        service.open_file(str(executable))


def test_settings_roundtrip(service):
    updated = service.update_settings({"ocr_enabled": True, "bulk_confirm_threshold": 8})
    assert updated.ocr_enabled is True
    assert updated.bulk_confirm_threshold == 8
    assert service.stats()["settings"]["bulk_confirm_threshold"] == 8


@pytest.mark.asyncio
async def test_summarize_without_ai_is_honest(service, docs):
    service.index_directory()
    summary = await service.summarize(str(docs / "apollo-notes.txt"), use_ai=False)
    assert summary["ai_used"] is False
    assert "Apollo" in summary["summary"]


def test_no_delete_capability_exists(service):
    assert not hasattr(service, "delete")
    assert not hasattr(service, "delete_file")
    assert not hasattr(service, "remove_file")
