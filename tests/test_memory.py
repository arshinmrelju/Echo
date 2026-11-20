from echo.memory.store import MemoryStore


def test_memory_add_and_list(memory_store: MemoryStore):
    entry = memory_store.add_memory(
        category="fact",
        key="user_name",
        content="The user's name is Alex.",
    )
    assert entry.id is not None
    assert entry.key == "user_name"
    assert entry.sensitivity == "normal"

    entries = memory_store.list_memories()
    assert len(entries) == 1
    assert entries[0].key == "user_name"


def test_memory_fts_search(memory_store: MemoryStore):
    memory_store.add_memory(category="project", key="project_apollo", content="Apollo is a Python AI assistant.")
    memory_store.add_memory(category="preference", key="editor", content="Prefers dark theme in VS Code.")

    results = memory_store.list_memories(query="Apollo")
    assert len(results) == 1
    assert results[0].key == "project_apollo"


def test_memory_sensitive_filtering(memory_store: MemoryStore):
    memory_store.add_memory(
        category="fact",
        key="api_secret_token",
        content="secret_12345",
    )
    entries = memory_store.list_memories()
    assert entries[0].sensitivity == "high"

    # Verify context string excludes high-sensitivity items
    context = memory_store.get_memory_context()
    assert "secret_12345" not in context


def test_memory_deletion(memory_store: MemoryStore):
    entry = memory_store.add_memory(category="fact", key="temp", content="Temporary note.")
    deleted = memory_store.delete_memory(entry.id)
    assert deleted is True

    entries = memory_store.list_memories()
    assert len(entries) == 0

