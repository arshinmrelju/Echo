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
