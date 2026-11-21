import httpx
import pytest
from echo.api.app import app


@pytest.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_healthz_endpoint(async_client):
    res = await async_client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_system_status_endpoint(async_client):
    res = await async_client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["version"] == "0.1.0"
    assert "ai_provider" in data


@pytest.mark.asyncio
async def test_system_metrics_endpoint(async_client):
    res = await async_client.get("/api/v1/system/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "cpu_percent" in data
    assert "memory_percent" in data
    assert "disk_percent" in data


@pytest.mark.asyncio
async def test_conversations_crud(async_client):
    # 1. Create
    res = await async_client.post("/api/v1/conversations", json={"title": "Test Chat"})
    assert res.status_code == 200
    conv = res.json()
    conv_id = conv["id"]
    assert conv["title"] == "Test Chat"

    # 2. List
    res = await async_client.get("/api/v1/conversations")
    assert res.status_code == 200
    items = res.json()
    assert any(c["id"] == conv_id for c in items)

    # 3. Get Detail
    res = await async_client.get(f"/api/v1/conversations/{conv_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == conv_id
    assert detail["messages"] == []

    # 4. Update
    res = await async_client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Updated Title"})
    assert res.status_code == 200
    assert res.json()["title"] == "Updated Title"

    # 5. Delete
    res = await async_client.delete(f"/api/v1/conversations/{conv_id}")
    assert res.status_code == 200

    # 6. Verify Deleted
    res = await async_client.get(f"/api/v1/conversations/{conv_id}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_memory_api(async_client):
    res = await async_client.post(
        "/api/v1/memory",
        json={"category": "preference", "key": "color_scheme", "content": "Prefers cyan/blue neon theme."},
    )
    assert res.status_code == 200
    entry = res.json()
    m_id = entry["id"]

    res = await async_client.get("/api/v1/memory?category=preference")
    assert res.status_code == 200
    items = res.json()
    assert any(m["id"] == m_id for m in items)

    res = await async_client.delete(f"/api/v1/memory/{m_id}")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_settings_api(async_client):
    res = await async_client.get("/api/v1/settings")
    assert res.status_code == 200
    settings = res.json()
    assert "ai_provider" in settings
    assert "ai_model" in settings

    res = await async_client.put("/api/v1/settings", json={"ai_temperature": 0.5, "theme": "dark"})
    assert res.status_code == 200
    updated = res.json()
    assert updated["ai_temperature"] == 0.5
    assert updated["theme"] == "dark"


@pytest.mark.asyncio
async def test_tasks_api(async_client):
    res = await async_client.post("/api/v1/tasks", json={"goal": "Index local documents"})
    assert res.status_code == 200
    task = res.json()
    t_id = task["id"]
    assert task["status"] == "created"

    res = await async_client.patch(f"/api/v1/tasks/{t_id}", json={"status": "completed"})
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    res = await async_client.delete(f"/api/v1/tasks/{t_id}")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_memory_api_lifecycle(async_client, monkeypatch, temp_db):
    from echo.memory.store import MemoryStore

    store = MemoryStore(db=temp_db)
    monkeypatch.setattr("echo.api.routes.memory.get_memory_store", lambda: store)

    res = await async_client.post(
        "/api/v1/memory",
        json={"category": "fact", "key": "api_secret_token", "content": "secret value"},
    )
    assert res.status_code == 422

    res = await async_client.post(
        "/api/v1/memory",
        json={
            "category": "fact",
            "key": "api_secret_token",
            "content": "rotated token value",
            "allow_sensitive": True,
            "pinned": True,
            "tags": ["credentials"],
        },
    )
    assert res.status_code == 200
    entry = res.json()
    memory_id = entry["id"]
    assert entry["sensitivity"] == "high"
    assert entry["permission_granted"] is True
    assert entry["pinned"] is True

    res = await async_client.patch(
        f"/api/v1/memory/{memory_id}",
        json={"content": "rotated again", "pinned": False},
    )
    assert res.status_code == 200
    assert res.json()["pinned"] is False

    res = await async_client.get("/api/v1/memory/stats")
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["sensitive"] == 1

    res = await async_client.get("/api/v1/memory/export")
    assert res.status_code == 200
    assert res.json()["count"] == 1

    res = await async_client.post("/api/v1/memory/clear", json={"confirm": False})
    assert res.status_code == 400

    res = await async_client.post(
        "/api/v1/memory/clear", json={"category": "fact", "confirm": True}
    )
    assert res.status_code == 200
    assert res.json()["removed"] == 1


@pytest.mark.asyncio
async def test_files_api_workflow(async_client, monkeypatch, temp_db, temp_dir):
    from echo.files.service import FileIntelligenceService

    service = FileIntelligenceService(db=temp_db)
    monkeypatch.setattr("echo.api.routes.files.get_file_service", lambda: service)

    root = temp_dir / "api-docs"
    root.mkdir()
    (root / "report.txt").write_text("Quarterly report about Apollo.", encoding="utf-8")
    (root / "second.txt").write_text("Second note.", encoding="utf-8")
    (root / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    res = await async_client.post(
        "/api/v1/files/directories",
        json={"path": str(root), "label": "API docs", "index_now": True},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["directory"]["file_count"] == 3
    assert payload["index"]["indexed"] == 3

    res = await async_client.get("/api/v1/files/search", params={"q": "Apollo"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["results"][0]["name"] == "report.txt"

    res = await async_client.get("/api/v1/files/categories")
    assert res.status_code == 200
    categories = {item["category"]: item["count"] for item in res.json()["categories"]}
    assert categories["document"] == 2
    assert categories["spreadsheet"] == 1

    res = await async_client.get("/api/v1/files/details", params={"path": str(root / "report.txt")})
    assert res.status_code == 200
    assert "Apollo" in res.json()["preview"]

    outside = temp_dir / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    res = await async_client.get("/api/v1/files/details", params={"path": str(outside)})
    assert res.status_code == 403

    res = await async_client.put(
        "/api/v1/files/settings", json={"bulk_confirm_threshold": 2}
    )
    assert res.status_code == 200

    res = await async_client.post(
        "/api/v1/files/organize",
        json={"directory": str(root), "dry_run": True},
    )
    assert res.status_code == 200
    assert res.json()["planned"] == 3

    res = await async_client.post(
        "/api/v1/files/organize",
        json={"directory": str(root), "dry_run": False, "confirm": False},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["plan"]["planned"] == 3

    res = await async_client.get("/api/v1/files/activity")
    assert res.status_code == 200
    actions = {item["action"] for item in res.json()["actions"]}
    assert "index" in actions
    assert "directory.add" in actions

