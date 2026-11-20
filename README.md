# ECHO — Personal AI Assistant

> A local-first, Windows-native AI agent that can see, hear, remember, act — and ask before it does something that matters.

**Status:** Stage 1 — ECHO Core Functional & Verified.
The core desktop application is runnable, with active WebSocket streaming, local SQLite persistence (WAL mode), persistent memory vault, dynamic AI model routing (Mock / Ollama / OpenAI-compatible), full configuration management, and a futuristic dark Command Center UI.

---

## Why ECHO is not a chatbot

A chatbot answers. ECHO **operates**.

ECHO is designed as a persistent personal agent that runs on the user's Windows machine, understands intent, plans multi-step work, calls explicitly defined tools, verifies the result, remembers what matters, monitors the system, and reaches the user remotely when something needs attention.

It is built around one rule:

> **The model may propose actions. Only the runtime may perform them.**

---

## Implemented Core Features (Stage 1)

1. **ECHO Futuristic Command Center UI:**
   - Dark, obsidian and neon cyan aesthetic (`#05070A`, `#00F0FF`, `#0070F3`).
   - Living status orb reflecting daemon state (`idle`, `thinking`, `speaking`, `executing`, `error`).
   - Conversation history list with persistent storage, real-time message counter, and deletion controls.
   - Rich Markdown message rendering with copy buttons, timestamps, streaming cursors, and syntax-highlighted code blocks.
   - Generation controls: stop generation button and retry response.
   - Collapsible telemetry drawer with live workstation metrics (CPU, RAM, Disk, Uptime).

2. **AI Provider Abstraction (`echo/brain`):**
   - Pluggable `ModelProvider` interface supporting streaming completions.
   - **Deterministic Mock Provider:** Built-in offline testing provider with realistic conversational streaming and status reporting.
   - **OpenAI-Compatible Provider:** Connects to OpenAI, OpenRouter, DeepSeek, LM Studio, or vLLM endpoints.
   - **Local Ollama Provider:** Direct HTTP integration (`127.0.0.1:11434`) for offline local neural models.
   - Dynamic prompt generation injecting recalled persistent memory context.

3. **Persistent Memory Vault (`echo/memory`):**
   - Categorized knowledge store (`fact`, `project`, `preference`, `context`).
   - SQLite FTS5 full-text search indexing for sub-millisecond retrieval.
   - Automatic classification and protection of sensitive information (passwords, private keys, auth tokens excluded from general context).
   - Interactive Memory Explorer UI modal to search, inspect, add, and delete memories.

4. **Task & Goal Queue (`echo/api/routes/tasks.py`):**
   - Dedicated task tracking system supporting goal creation, status transitions, and lifecycle tracking.
   - Tasks modal UI to inspect, complete, or remove tasks.

5. **Local-First SQLite Architecture (`echo/core/database.py`):**
   - SQLite 3 running in Write-Ahead Logging (WAL) mode with busy timeout handling.
   - Automated versioned schema migrations (`schema_version`).
   - Clean data persistence under `%LOCALAPPDATA%\Echo\data\echo.db` (with automatic fallback to `./data/`).

6. **FastAPI Loopback Daemon & WebSocket Gateway (`echo/api`):**
   - Bound strictly to `127.0.0.1`.
   - REST endpoints for health checks (`/healthz`, `/readyz`), system status, metrics, conversations, memory, tasks, and settings.
   - High-throughput WebSocket endpoint (`/api/v1/ws`) for bidirectional streaming, heartbeats, and stop commands.

---

## Getting Started & Development

### Prerequisites
- **OS:** Windows 10 (22H2+) or Windows 11
- **Python:** 3.11+
- **Node.js:** 20+ LTS

### 1. Installation

```powershell
# Create Python virtual environment and install backend dependencies
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Install frontend dependencies
npm --prefix frontend install
```

### 2. Configuration

Copy the example environment file:
```powershell
cp .env.example .env
```

Key environment variables:
- `ECHO_HOST=127.0.0.1`: Daemon host binding (loopback).
- `ECHO_PORT=8000`: Daemon port.
- `ECHO_AI_PROVIDER=mock`: Active provider (`mock`, `ollama`, `openai`).
- `ECHO_AI_MODEL=echo-fast-v1`: Active model identifier.
- `ECHO_AI_API_KEY`: API key for external cloud models (optional, can also be configured via UI).

### 3. Running in Development Mode

Run both the backend daemon and the frontend UI concurrently using the provided script:
```powershell
.\scripts\dev.ps1
```
Or start them in separate terminals:

**Terminal 1 (Backend Daemon):**
```powershell
.\.venv\Scripts\python -m uvicorn echo.api.app:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 (Frontend Command Center):**
```powershell
cd frontend
npm run dev
```
Open **`http://127.0.0.1:5173`** in your browser.

### 4. Running the Test Suite

```powershell
.\scripts\test.ps1
```
Or directly with pytest:
```powershell
.\.venv\Scripts\pytest -o pythonpath=. -v
```

---

## Roadmap Summary

| Stage | Theme | Status |
|---|---|---|
| 0 | Architecture, security model, UI direction, roadmap | ✅ Complete |
| 1 | Foundation: ECHO Core (Daemon, SQLite WAL, UI Shell, Memory, Brain) | ✅ Complete |
| 2 | Advanced AI Brain & Multi-Provider Streaming Reasoning | Planned |
| 3 | Advanced Episodic & Procedural Memory with Vector Embeddings | Planned |
| 4 | Tools, Permissions (T0–T4) & Hash-Chained Audit Trails | Planned |
| 5 | Agent Planner & Verification Runtime State Machine | Planned |
| 6 | File Intelligence & Safe Operations | Planned |
| 7 | Desktop Control & Windows UI Automation | Planned |
| 8 | Browser Automation (Playwright Sandboxing) | Planned |
| 9 | Voice Interaction (openWakeWord, Whisper, Piper) | Planned |
| 10 | Monitoring & Notifications (Event Log, Hardware Telemetry) | Planned |
| 11 | Scheduler & Autonomous Routines | Planned |
| 12 | Remote Contact & Escalation Calls | Planned |
| 13 | Desktop Packaging, Hardening & Release | Planned |

---

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, 14 modules, SQLite schema, IPC protocols. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Detailed acceptance criteria and definitions of done for Stages 0–13. |
| [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md) | Trust boundaries, STRIDE threat analysis, prompt injection defense. |
| [docs/TOOL-CONTRACT.md](docs/TOOL-CONTRACT.md) | Pydantic schemas, 7-step execution pipeline, verification rules. |
| [docs/UI-DESIGN.md](docs/UI-DESIGN.md) | Visual tokens, dark futuristic palette, screen architecture. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture Decision Records (ADRs 001–006). |
