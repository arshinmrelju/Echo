# ECHO — System Architecture

> **Document Status:** Stage 0 Complete  
> **Last Updated:** November 2026  
> **Applies To:** ECHO Core v0.1.0+

---

## 1. System Vision & Architectural Invariants

ECHO is a **local-first, Windows-native autonomous personal AI assistant**. Unlike conversational chatbots that generate passive text, ECHO is an **operational agent** capable of reasoning, breaking down complex objectives into sequential tool invocations, observing environment feedback, verifying results, and maintaining situational awareness over background operating system events.

### The Golden Rule of Execution
$$\text{Model proposes} \xrightarrow{\text{Schema Validation}} \xrightarrow{\text{Permission Evaluation}} \xrightarrow{\text{Approval Gate}} \text{Runtime executes} \xrightarrow{\text{Verification}} \text{Audit recorded}$$

Under no circumstances does an LLM execute raw shell code, PowerShell strings, or arbitrary binaries directly. Every side effect is mediated through strictly typed, declarative tool contracts with pre- and post-condition verification.

---

## 2. Process & Communication Model

ECHO uses a **decoupled daemon architecture**. The core logic, monitoring, scheduler, and agent execution live in a persistent Python background service. The user interface connects as a client. If the user closes the window, background watchers, scheduled automations, and remote escalation pipelines continue uninterrupted.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Windows Desktop Shell                         │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ Electron Process (isolated renderer, nodeIntegration: false)   │   │
│   │ ┌────────────────────────────────────────────────────────────┐ │   │
│   │ │ React 18 + Vite + TypeScript + Tailwind CSS UI             │ │   │
│   │ │ Command Center · Task Visualizer · Memory Explorer · Audit │ │   │
│   │ └──────────────────────────────┬─────────────────────────────┘ │   │
│   └────────────────────────────────┼───────────────────────────────┘   │
│                                    │ Loopback Only (127.0.0.1)         │
│                                    │ Per-session Token Bearer Auth     │
│                                    │ REST (CRUD) + WebSocket (Events)  │
│   ┌────────────────────────────────▼───────────────────────────────┐   │
│   │ ECHO Core Daemon (Python 3.12+ / FastAPI / AsyncIO)            │   │
│   │                                                                │   │
│   │  ┌───────────────┐  ┌──────────────────┐  ┌─────────────────┐  │   │
│   │  │ Kernel/Events │  │ Security/Authz   │  │ Audit Logger    │  │   │
│   │  └───────┬───────┘  └────────┬─────────┘  └────────┬────────┘  │   │
│   │          │                   │                     │           │   │
│   │  ┌───────▼───────────────────▼─────────────────────▼────────┐  │   │
│   │  │               Agent Orchestrator & Planner               │  │   │
│   │  │ (State Machine · Budget Guard · Verification Gate)       │  │   │
│   │  └───────┬───────────────────┬─────────────────────┬────────┘  │   │
│   │          │                   │                     │           │   │
│   │  ┌───────▼───────┐  ┌────────▼─────────┐  ┌────────▼────────┐  │   │
│   │  │ AI Brain      │  │ Tool Registry    │  │ Memory Engine   │  │   │
│   │  │ (Local/Cloud) │  │ (T0 - T4 Tiers)  │  │ (Episodic/FTS5) │  │   │
│   │  └───────────────┘  └────────┬─────────┘  └─────────────────┘  │   │
│   │                              │                                 │   │
│   │   ┌──────────────────────────┼────────────────────────────┐    │   │
│   │   ▼                          ▼                            ▼    │   │
│   │ Desktop Control      File Intelligence            Browser      │   │
│   │ (WinUI/pywinauto)    (Safe Indexer/Ops)           (Playwright) │   │
│   │                                                                │   │
│   │   ┌───────────────────────────────────────────────────────┐    │   │
│   │   │ Background Workers (Voice · Monitoring · Scheduler)   │    │   │
│   │   └───────────────────────────────────────────────────────┘    │   │
│   └────────────────────────────────┬───────────────────────────────┘   │
│                                    │ SQLite 3 (WAL mode)               │
│                                    │ Windows Credential Manager        │
│                                    ▼                                   │
│                     %LOCALAPPDATA%\Echo\data                           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The 14 Modular Subsystems

Each subsystem is an isolated package under `echo/` with explicit public interfaces, internal data structures, and graceful degradation mechanics.

### 1. AI Brain (`echo/brain`)
* **Role:** Abstract language model provider orchestration, prompt assembly, token budgeting, and streaming.
* **Supported Providers:**
  * **Ollama (Default / Free / Local):** High performance local inference via Ollama HTTP API (`/api/chat`).
  * **OpenAI-Compatible (Local or Cloud):** LM Studio, vLLM, DeepSeek, Anthropic, or OpenAI endpoints.
  * **Deterministic Fake Provider:** In-memory mock for zero-cost hermetic unit and integration testing.
* **Key Contracts:**
  * `ModelProvider` ABC defining `stream_chat(messages, tools, options) -> AsyncIterator[ChatChunk]`.
  * `PromptEngine` assembling system policy, personality, working memory, and tool definitions into model-specific formats.
  * `ContextGuard` tracking token windows, calculating degradation cutoffs, and executing rolling context summarization.

### 2. Agent Planner & Runtime (`echo/agent`)
* **Role:** Multi-step deterministic plan formation, goal decomposition, execution loop, and failure recovery.
* **State Machine:**
  `CREATED` $\to$ `PLANNING` $\to$ `AWAITING_APPROVAL` $\to$ `EXECUTING_TOOL` $\to$ `OBSERVING` $\to$ `VERIFYING` $\to$ `COMPLETED` / `FAILED` / `CANCELLED`
* **Invariants:**
  * Step Limits: Maximum steps per run (configurable default: 15) to prevent infinite reasoning loops.
  * Wall-Clock & Cost Budgets: Enforced hard timeouts on task execution.
  * Checkpointing: State persisted to SQLite before and after every step. Tasks can safely pause and resume across daemon restarts.

### 3. Tool Execution Engine (`echo/tools`)
* **Role:** Central catalog, validation gateway, and sandboxed runner for all external side effects.
* **Pipeline:**
  1. Input parameter validation against strict Pydantic schemas.
  2. Permission checking against active session policies and user grants.
  3. Preflight sanity check (e.g., verifying target file path isn't a symlink out of bounds).
  4. User approval trigger if tool tier requires consent.
  5. Isolated execution with timeout enforcement.
  6. Post-execution verification (never trust tool return code blindly).
  7. Hash-chained audit logging.

### 4. Memory Subsystem (`echo/memory`)
* **Role:** Multi-tier storage representing working state, short-term interactions, and long-term knowledge.
* **Tiers:**
  * **Working Memory:** In-memory scratchpad active during a single task or conversation turn.
  * **Episodic Memory:** Immutable log of conversations, user feedback, and completed task summaries.
  * **Semantic Memory:** Extracted atomic facts, preferences, user habits, and system environment realities.
* **Retrieval Engine:** Hybrid search using SQLite FTS5 (BM25 keyword matching) combined with dense vector embeddings via local ONNX/fastembed models, ranked via Reciprocal Rank Fusion (RRF).

### 5. Desktop Control (`echo/desktop`)
* **Role:** Native Windows interaction without brittle coordinate-only guessing.
* **Design:**
  * **Primary:** Windows UI Automation (UIA) via `pywinauto` to locate elements by accessibility names, control types, and AutomationIDs.
  * **Fallback:** Computer vision / OCR-guided visual clicking (`mss` screenshot capture + Windows Media OCR / Tesseract).
  * **Safeguards:** Screen bounds validation, DPI awareness, failsafe cursor gestures (slamming cursor to screen corner triggers immediate halt), and mandatory user approval for typing into sensitive windows.

### 6. File Intelligence (`echo/files`)
* **Role:** Safe local document indexing, content extraction, and controlled file mutation.
* **Capabilities:**
  * Recursive watcher on designated project directories.
  * Parsers for Markdown, Plain Text, Code, PDF, DOCX, XLSX, and CSV.
  * Safe Operations: Read, search, summarize, copy, move, and recycle.
  * **Safety Invariant:** Never permanently delete files via raw unlink; always route deletions to the Windows Recycle Bin (`SHFileOperation` / `winshell`).

### 7. Browser Control (`echo/browser`)
* **Role:** Targeted web navigation, research, and authenticated workflows using Playwright Chromium.
* **Safeguards:**
  * Strict domain allowlisting configured per task.
  * Private network and local loopback address access (`localhost`, `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`) blocked by default to prevent Server-Side Request Forgery (SSRF).
  * Consequential actions (form submission, payment buttons, authentication changes) locked behind interactive user approvals.
  * Strict DOM accessibility snapshots used for LLM consumption instead of raw unstructured HTML dumps.

### 8. Voice Subsystem (`echo/voice`)
* **Role:** Low-latency, privacy-preserving hands-free audio interaction.
* **Stack:**
  * **Wake Word:** Local, offline detection using `openWakeWord` ("Hey Echo").
  * **Voice Activity Detection (VAD):** `Silero VAD` running locally to identify speech boundaries.
  * **Speech-to-Text (STT):** Local `faster-whisper` (int8 quantized models running on GPU or multi-threaded CPU).
  * **Text-to-Speech (TTS):** Local `Piper` neural TTS engine with low-latency Windows SAPI fallback.
  * **Barge-in:** Audio output stream instantly terminates when the VAD detects incoming user speech.

### 9. Monitoring Subsystem (`echo/monitoring`)
* **Role:** Continuous passive telemetry collection and rule evaluation over Windows environment health.
* **Watchers:**
  * Hardware & OS metrics (CPU, RAM, Disk, Battery, Network) via `psutil`.
  * Windows Event Log channels (System, Application, Security failures).
  * Process lifecycle events (detecting crashes or unauthorized process launches).
* **Rule Engine:** Declarative threshold triggers with configurable quiet hours, sliding-window deduplication, and storm suppression.

### 10. Notifications Subsystem (`echo/notifications`)
* **Role:** Dispatching alerts across appropriate delivery channels based on severity.
* **Channels:**
  * **Local Windows Toast Notifications:** Interactive native Windows toasts.
  * **Telegram Bot:** Secure long-polling bot delivering instant alerts to an allowlisted user chat ID.
  * **SMTP Email:** Structured HTML summary digests for non-urgent reports.
  * **Escalation Matrix:** Configurable cascading escalation (Toast $\to$ Telegram $\to$ SMS/Call).

### 11. Scheduler & Autonomy (`echo/scheduler`)
* **Role:** Time-triggered task dispatching and recurring autonomous maintenance.
* **Features:**
  * Supports Cron syntax, interval timers, and one-shot delayed executions.
  * Timezone-aware scheduling with explicit daylight saving time policies.
  * Missed-run policies: `SKIP`, `RUN_ONCE`, or `BURST`.
  * Autonomy Tiers: Supervised (pauses for approval on T2+ actions) vs. Trusted (runs pre-approved routines within strict resource budgets).

### 12. Permissions & Security Engine (`echo/permissions`)
* **Role:** Central gatekeeper enforcing least privilege, capability scoping, and consent verification.
* **Mechanism:**
  * Granular scopes: `file:read`, `file:write`, `desktop:interact`, `browser:navigate`, `system:monitor`, `network:external`.
  * Risk tiers T0 to T4.
  * Time-bound, session-bound, and single-use grants.
  * Cryptographic argument hashing: user approval is bound to specific tool arguments. Replay with modified arguments is rejected.

### 13. User Interface (`frontend/` & `desktop/`)
* **Role:** Futuristic, high-density AI Command Center providing real-time visibility and control.
* **Tech:** React 18, TypeScript, Tailwind CSS, Lucide icons, Vite build toolchain, wrapped in an Electron desktop shell.
* **Visual Tone:** Obsidian dark theme (`#080B10`), neon cyan accents (`#00F0FF`), deep cobalt secondary glow (`#0070F3`), monospace telemetry type, clean glassmorphic panels, and animated status orbs.

### 14. Logging & Auditing (`echo/audit` & `echo/core/logging`)
* **Role:** Tamper-evident, non-repudiable audit recording of all AI reasoning and tool execution.
* **Properties:**
  * Structured JSON logs with unique trace and correlation IDs.
  * Append-only SQLite audit table with SHA-256 hash chaining ($Hash_n = \text{SHA256}(Hash_{n-1} + \text{Record}_n)$).
  * Automatic redaction of sensitive credentials, API keys, and private tokens before disk writing.

---

## 4. SQLite Data Architecture & Persistence

Data is stored locally under `%LOCALAPPDATA%\Echo\data\echo.db` using **SQLite with Write-Ahead Logging (WAL)**.

```sql
-- Schema Overview

-- 1. Conversation & Message Persistence
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP NOT NULL,
    metadata JSON
);

-- 2. Task State & Agent Steps
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('created', 'planning', 'awaiting_approval', 'executing', 'verifying', 'completed', 'failed', 'cancelled')),
    step_count INTEGER DEFAULT 0,
    max_steps INTEGER DEFAULT 15,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    error TEXT
);

CREATE TABLE IF NOT EXISTS task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    thought TEXT,
    tool_name TEXT,
    tool_args JSON,
    tool_result JSON,
    verification_status TEXT CHECK(verification_status IN ('unverified', 'verified', 'failed')),
    verification_details TEXT,
    created_at TIMESTAMP NOT NULL
);

-- 3. Memory & Semantic Knowledge
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('working', 'episodic', 'semantic', 'procedural')),
    scope TEXT NOT NULL DEFAULT 'global',
    key TEXT,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    importance REAL DEFAULT 0.5,
    sensitivity TEXT DEFAULT 'normal' CHECK(sensitivity IN ('low', 'normal', 'high', 'secret')),
    created_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    key,
    scope,
    content='memories',
    content_rowid='rowid'
);

-- 4. Cryptographic Hash-Chained Audit Trail
CREATE TABLE IF NOT EXISTS audit_log (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TIMESTAMP NOT NULL,
    correlation_id TEXT NOT NULL,
    actor TEXT NOT NULL CHECK(actor IN ('user', 'agent', 'system', 'remote')),
    action TEXT NOT NULL,
    target TEXT,
    risk_tier TEXT NOT NULL,
    parameters JSON,
    result TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL
);

-- 5. Scheduled Jobs
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cron_expression TEXT,
    interval_seconds INTEGER,
    task_template JSON NOT NULL,
    autonomy_level TEXT NOT NULL CHECK(autonomy_level IN ('manual', 'supervised', 'trusted')),
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP
);
```

---

## 5. Failure Handling & Degradation Matrix

ECHO is architected to remain functional even when individual dependencies are missing or fail:

| Component Outage | Impact | Mitigation Strategy |
|---|---|---|
| **Ollama / Local LLM Down** | AI reasoning fails | UI flags model offline, offers setup guide, switches to configured cloud fallback if permitted. |
| **Microphone / Audio Missing** | Voice interaction disabled | Voice subsystem degrades cleanly; chat prompt bar and keyboard hotkeys remain primary. |
| **Playwright Not Installed** | Browser automation unavailable | Browser tools report clear diagnostic error; other tools and general tasks remain active. |
| **UIA Driver Blocked** | Direct desktop automation restricted | Falls back to visual OCR clicker or prompts user for manual execution with guided steps. |
| **Internet / Network Offline** | External APIs & Telegram down | Local-first core functions identically: local models, desktop tools, and local alerts run normally. |
| **Database Lock / Contention** | SQLite concurrency conflict | SQLite WAL mode with 5000ms busy-timeout retry handles high concurrency smoothly. |

