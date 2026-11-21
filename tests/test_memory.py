import pytest

from echo.memory.store import MemoryStore, is_sensitive_text


def test_memory_add_and_list(memory_store: MemoryStore):
    entry = memory_store.add_memory(
        category="fact",
        key="user_name",
        content="The user's name is Alex.",
    )
    assert entry.id is not None
    assert entry.key == "user_name"
    assert entry.sensitivity == "normal"
    assert entry.source == "user"
    assert entry.permission_granted is False

    entries = memory_store.list_memories()
    assert len(entries) == 1
    assert entries[0].key == "user_name"
    assert entries[0].created_at


def test_memory_fts_search(memory_store: MemoryStore):
    memory_store.add_memory(category="project", key="project_apollo", content="Apollo is a Python AI assistant.")
    memory_store.add_memory(category="preference", key="editor", content="Prefers dark theme in VS Code.")

    results = memory_store.list_memories(query="Apollo")
    assert len(results) == 1
    assert results[0].key == "project_apollo"

    prefixed = memory_store.list_memories(query="pref")
    assert any(entry.key == "editor" for entry in prefixed)


def test_memory_sensitive_filtering_requires_permission(memory_store: MemoryStore):
    with pytest.raises(ValueError):
        memory_store.add_memory(
            category="fact",
            key="api_secret_token",
            content="secret_12345",
        )

    # Underscored / hyphenated keys are still normalized and detected.
    assert is_sensitive_text("api_secret_token")

    # Bare token assignments count as credentials even without an api_/auth_ prefix.
    assert is_sensitive_text("token=abc123supersecret")
    with pytest.raises(ValueError):
        memory_store.add_memory(
            category="fact",
            key="service_token",
            content="token=abc123supersecret",
        )

    entry = memory_store.add_memory(
        category="fact",
        key="api_secret_token",
        content="secret_12345",
        allow_sensitive=True,
    )
    assert entry.sensitivity == "high"
    assert entry.permission_granted is True

    # High-sensitivity entries never leak into the model context.
    context = memory_store.get_memory_context()
    assert "secret_12345" not in context

    stats = memory_store.stats()
    assert stats["sensitive"] == 1


def test_memory_all_categories_and_stats(memory_store: MemoryStore):
    memory_store.add_memory(category="preference", key="tone", content="Prefers concise replies.")
    memory_store.add_memory(category="project", key="project.echo", content="ECHO is a local desktop agent.")
    memory_store.add_memory(category="task", key="task:1", content="Indexed documents.", source="task")
    memory_store.add_memory(
        category="conversation",
        key="conversation:1",
        content="Discussed memory provenance.",
        source="conversation",
    )

    stats = memory_store.stats()
    assert stats["total"] == 4
    assert stats["by_category"]["task"] == 1
    assert stats["by_category"]["conversation"] == 1
    assert stats["by_source"]["task"] == 1
    assert stats["last_updated_at"]

    for category in ("task", "conversation", "project", "preference"):
        entries = memory_store.list_memories(category=category)
        assert entries and entries[0].category == category


def test_memory_update_pin_and_archive(memory_store: MemoryStore):
    first = memory_store.add_memory(category="preference", key="theme", content="Dark theme.")
    second = memory_store.add_memory(category="fact", key="timezone", content="UTC+3.")

    updated = memory_store.update_memory(
        second.id,
        content="UTC+4 (summer time).",
        pinned=True,
        tags=["schedule"],
    )
    assert updated.content == "UTC+4 (summer time)."
    assert updated.pinned is True
    assert updated.tags == ["schedule"]

    listed = memory_store.list_memories()
    assert listed[0].id == second.id  # pinned first

    memory_store.update_memory(first.id, archived=True)
    visible = memory_store.list_memories()
    assert all(entry.id != first.id for entry in visible)
    archived = memory_store.list_memories(include_archived=True)
    assert any(entry.id == first.id and entry.archived for entry in archived)


def test_memory_export_and_clear(memory_store: MemoryStore):
    memory_store.add_memory(category="fact", key="one", content="Entry one.")
    memory_store.add_memory(category="project", key="two", content="Entry two.")

    exported = memory_store.export_memories()
    assert exported["count"] == 2
    assert len(exported["memories"]) == 2
    assert exported["memories"][0]["created_at"]

    removed = memory_store.clear_memories(category="fact")
    assert removed == 1
    assert memory_store.stats()["total"] == 1

    removed = memory_store.clear_memories()
    assert removed == 1
    assert memory_store.stats()["total"] == 0
    assert memory_store.export_memories()["count"] == 0


def test_memory_context_uses_provenance_and_counts_usage(memory_store: MemoryStore):
    memory_store.add_memory(category="preference", key="editor", content="Uses VS Code.", pinned=True)
    memory_store.add_memory(category="fact", key="day", content="Today is Tuesday.")

    context = memory_store.get_memory_context(query="VS Code")
    assert "[PREFERENCE" in context
    assert "editor: Uses VS Code." in context
    assert "| user |" in context or "· user ·" in context

    entries = memory_store.list_memories()
    used = next(entry for entry in entries if entry.key == "editor")
    assert used.use_count >= 1
    assert used.last_used_at is not None


def test_task_memory_capture(memory_store: MemoryStore):
    entry = memory_store.record_task_memory(
        task_id="task-123",
        goal="Index the documents folder",
        status="completed",
    )
    assert entry is not None
    assert entry.category == "task"
    assert entry.source == "task"
    assert "Index the documents folder" in entry.content
    assert "completed" in entry.content

    failed = memory_store.record_task_memory(
        task_id="task-456",
        goal="Organize downloads",
        status="failed",
        error="Destination was not approved.",
    )
    assert failed is not None
    assert "Destination was not approved." in failed.content


def test_conversation_summary_capture(memory_store: MemoryStore):
    summary = memory_store.build_conversation_summary(
        [
            {"role": "user", "content": "Remember that my project is ECHO."},
            {"role": "assistant", "content": "Noted. ECHO is your local desktop agent."},
        ]
    )
    assert "User: Remember that my project is ECHO." in summary
    assert "ECHO: Noted." in summary

    entry = memory_store.record_conversation_summary(
        conversation_id="conv-1",
        summary=summary,
        message_count=2,
        title="Project context",
    )
    assert entry is not None
    assert entry.category == "conversation"
    assert entry.source == "conversation"
    assert any(tag.startswith("messages:") for tag in entry.tags)

    results = memory_store.list_memories(query="local desktop agent")
    assert any(item.id == entry.id for item in results)


def test_memory_deletion(memory_store: MemoryStore):
    entry = memory_store.add_memory(category="fact", key="temp", content="Temporary note.")
    deleted = memory_store.delete_memory(entry.id)
    assert deleted is True

    entries = memory_store.list_memories()
    assert len(entries) == 0
