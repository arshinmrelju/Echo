# ECHO — System Architecture

> **Document Status:** Stage 6 Memory & File Intelligence Implemented  
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

## 3. The 15 Modular Subsystems

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
* **Role:** Inspectable long-term knowledge with explicit provenance, plus automatic task and conversation capture.
* **Categories:** `fact`, `project`, `preference`, `context`, `task`, and `conversation`. Personal, project, task, and conversation memory are all stored in the same SQLite table and surfaced through one explorer.
* **Storage:** `memories` plus an FTS5 index (`memories_fts`) over key, content, category, and tags. Prefix matching (FTS tokens are suffixed with `*`) provides keyword search without an embedding model.
* **Provenance:** Every entry records `source` (`user`, `task`, `conversation`), `created_at`/`updated_at`, confidence, tags, pin/archive state, `last_used_at`, and `use_count`.
* **Sensitivity gate:** Writes are scanned for credentials and high-risk personal data (normalizing `_`/`-` to spaces). Matching writes are refused unless the user explicitly grants permission; permitted entries are marked `sensitivity=high` and excluded from automatic model context. Secret values that pass through task/conversation capture are redacted first.
* **Retrieval:** `get_memory_context` combines FTS matches, pinned entries, recent conversation summaries, and recent entries, skipping high-sensitivity rows. Semantic/vector retrieval and reciprocal rank fusion remain an optional future extension.
* **Rules enforced:** ECHO never claims to remember anything absent from this store; the explorer exposes view, search, edit, pin, archive, delete, export, and clear; clear and delete are explicitly confirmed.

### 5. Desktop Control (`echo/desktop`)
* **Role:** Native Windows interaction without brittle coordinate-only guessing.
* **Design:**
  * **Primary:** Windows UI Automation (UIA) via `pywinauto` to locate elements by accessibility names, control types, and AutomationIDs.
  * **Fallback:** Computer vision / OCR-guided visual clicking (`mss` screenshot capture + Windows Media OCR / Tesseract).
  * **Safeguards:** Screen bounds validation, DPI awareness, failsafe cursor gestures (slamming cursor to screen corner triggers immediate halt), and mandatory user approval for typing into sensitive windows.

### 6. File Intelligence (`echo/files`)
* **Role:** Search, inspect, and safely mutate local files strictly inside directories the user has approved.
* **Containment:** `approved_directories` is the only entry point. Paths are canonicalized with `Path.resolve()` and rejected unless contained by an enabled root; drive roots and protected system paths are refused. Search, details, and every action re-check containment. Removing a root stops future indexing without touching disk.
* **Indexing:** Explicit index runs (no background watcher) record name, extension, category, size, timestamps, SHA-256, extracted text, and metadata. Credential files (`.env`, keys, keystores, `credentials.json`) are skipped; extracted text is secret-redacted.
* **Extraction:** Standard-library readers for text/code, CSV/TSV, DOCX, XLSX, and PPTX; optional `pypdf` for PDF text and `pytesseract` for image OCR. Capability reporting states honestly what is installed. Images always yield metadata through Pillow when available.
* **Search:** Filename/path/content matching with category, extension, size, date, sort, and approved-root filters; duplicate detection groups rows by content hash and size; large-file and category statistics come from the same index.
* **Actions:** Open, rename, copy, move, organize by category, bulk rename, summarize, and duplicate quarantine. Every action is audited in `file_actions`.
* **Safety invariant:** ECHO never deletes. Duplicate quarantine moves extra copies into `_ECHO_DUPLICATES` and always keeps one copy; directory removal only unlinks the approval. Moves/renames that exceed the configured bulk threshold return HTTP 409 with a plan and require explicit confirmation (overwrites also confirm).

### 7. Browser Control (`echo/browser`)
* **Role:** Targeted web navigation, research, and authenticated workflows using Playwright Chromium.
* **Safeguards:**
  * Strict domain allowlisting configured per task.
  * Private network and local loopback address access (`localhost`, `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`) blocked by default to prevent Server-Side Request Forgery (SSRF).
  * Consequential actions (form submission, payment buttons, authentication changes) locked behind interactive user approvals.
  * Strict DOM accessibility snapshots used for LLM consumption instead of raw unstructured HTML dumps.

### 8. Voice Subsystem (`echo/voice`)
* **Role:** Low-latency, privacy-preserving hands-free audio interaction, owned by the daemon rather than the browser.
* **Runtime model:**
  * `VoiceService` is a process singleton bound to the daemon event loop. It persists voice settings and the last voice conversation in SQLite, exposes REST/WS controls, and owns at most one `VoiceSession`.
  * `VoiceSession` starts a `sounddevice` capture worker thread. The audio callback only copies frames into a bounded queue; endpointing, wake-word spotting, and barge-in detection run on the session thread so recognition never blocks capture.
  * Audio is converted to 16 kHz mono with linear resampling when the device does not open at that rate. Frames are never written to disk unless debug recordings are explicitly enabled.
  * Asynchronous work (STT, chat turn, TTS) is scheduled back onto the daemon loop; all state changes are broadcast through `ws_hub.ConnectionManager` as `voice_*` events.
* **Stack (implemented):**
  * **Wake Word:** local keyword spotting over short energy-gated segments using the same shared Whisper model, with fuzzy matching against the configured word and aliases. Default `echo`; sensitivity is configurable. openWakeWord remains a planned upgrade.
  * **Voice Activity Detection:** RMS energy gate with an adaptive noise floor, silence-based endpointing, minimum speech duration, and a hard utterance cap (`echo/voice/vad.py`).
  * **Speech-to-Text:** local `faster-whisper` (`tiny.en`, int8 CPU by default) loaded once per process and reused for wake spotting, partials, and finals.
  * **Text-to-Speech:** Windows SAPI through `pyttsx3` on a dedicated thread, with a sentence-chunked queue, voice/rate/volume selection, and immediate cancellation. Piper remains the planned neural upgrade.
  * **Barge-in:** sustained microphone energy during `SPEAKING` cancels the TTS queue and bumps a speech generation counter; an `AudioRingBuffer` pre-roll keeps the beginning of the interrupting utterance.
* **State machine:** `IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING`, `MUTED`, `ERROR`, with an explicit legal-transition graph. Modes are push-to-talk, wake word, and continuous; every path returns to `IDLE` on completion, dismissal, or timeout.
* **Data flow:**
  ```text
  mic frames → queue → VAD/endpoint → wake spot or utterance
            → faster-whisper → ChatTurnService (shared with text chat)
            → streaming reply → sentence chunks → pyttsx3 → speakers
  every transition → ws_hub → voice_state / voice_level / voice_transcript / voice_timing
  ```
* **Privacy invariants:**
  * Microphone and capture state are always reflected in `voice_status`/`voice_state`; the UI never has to guess.
  * Mute stops capture and transitions to `MUTED`; unmuting explicitly reopens the device.
  * Raw audio is memory-only by default. Optional WAV debug recordings require `save_recordings`, live under `%LOCALAPPDATA%\Echo\voice\recordings`, and are pruned by count.
  * No cloud speech provider is called; voice works with the network offline.
* **Degradation:** if `numpy`, `sounddevice`, `faster-whisper`, or `pyttsx3` are missing, `voice_status.installed` reports it and start fails with an actionable message; text chat, tools, and the rest of the daemon are unaffected.


### 9. Monitoring Subsystem (`echo/monitoring`)
* **Role:** Continuous passive telemetry collection, threshold evaluation, and alert lifecycle management, owned by the daemon and independent of the UI.
* **Engine (`engine.py`):** Async loop with a fast snapshot cadence and supervised slow-probe tasks. Snapshot collection runs in a worker thread; connectivity, temperature, and Event Log probes run concurrently so they never stall the main loop. Profiles (`quiet`, `balanced`, `strict`) reset thresholds/cadences, with per-field overrides persisted in `app_settings`.
* **Collectors (`collectors.py`):**
  * Hardware metrics (CPU, memory/swap, disks, battery, network rates, top processes) via `psutil`.
  * Reachability and latency against configurable `host:port` targets.
  * Optional thermal bridge (LibreHardwareMonitor/OpenHardwareMonitor WMI, then ACPI thermal zones) with explicit unavailability reporting.
  * Selected-process monitoring and Win32 hung-window detection.
  * Windows Event Log reads via `wevtutil` over System (allowlisted IDs) and Application Error/Hang, with lookback windows and informational-event downgrades.
* **Alert lifecycle (`alerting.py`, `store.py`):** Threshold persistence windows, stable dedupe keys, cooldown reminders, severity escalation, acknowledgement, manual resolution, hysteresis-based recovery, and automatic purge by retention. Active alerts and event history are stored in `monitor_alerts` / `monitor_events` (migration 2).
* **Surfaces:** REST `/api/v1/monitoring/*`, WebSocket `monitor_*` events/commands, and the System Observatory dashboard (overview, alerts, event feed, config).

### 10. Remote Relay (`echo/remote`)
* **Role:** Authenticated remote communication with the owner through Telegram, owned by the daemon and strictly outbound.
* **Transport (`telegram.py`, `service.py`):** Long polling via `httpx` against `getUpdates`; no webhook, no inbound listener, no public port. The update offset is persisted in `remote_state`, so restarts neither replay nor skip commands. Poll failures raise an explicit connectivity state, back off, and reconnect automatically.
* **Identity & pairing (`store.py`):** The bot token and numeric owner ID live in `app_settings`; responses mask the token. Explicit pairing uses a one-time 8-character code with a 5-minute TTL; only its SHA-256 hash is stored. Pairing transfers the single `owner` role once. Additional accounts may be added as `allowed`, which is read-only.
* **Command dispatch (`service.py`):**
  * Owner: `/ask`, `/task`, `/status`, `/health`, `/events`, `/tasks`, `/screenshot`, `/open`, `/approve`, `/deny`, `/pause`, `/resume`, `/pair`, `/whoami`, `/help`.
  * Allowed: `/status`, `/health`, `/events`, `/tasks`.
  * Private chats only. Unauthorized senders are rejected before dispatch and audited; commands are rate-limited per user (20/min) and audited on every outcome, including rate limiting.
  * Credential requests are pattern-blocked in questions, task goals, and free text before any model call.
* **Approvals:** Dangerous tools stay `APPROVAL_REQUIRED` in the shared `ToolRegistry`. A remote request creates a `remote_pending_actions` row bound to the Telegram ID, tool name, and arguments; `/approve <id>` and the desktop approval dialog both execute it exactly once. Approvals expire and cannot be replayed.
* **Remote tasks & screenshots:** Goals are recorded in `remote_tasks` and mirrored into the local `tasks` table. Screenshots route through `screen.capture_desktop`, are delivered only to the paired owner, and never to allowed users.
* **Notifications (`notifications.py`):** Alerts, recoveries, filtered monitor events, task results, approval requests, and connectivity changes are enqueued in SQLite with severity TTLs, dedupe keys, and exponential backoff. While Telegram is unreachable, rows remain queued; on reconnect, stale rows expire, duplicates collapse, overflow is suppressed, and one downtime summary replaces the backlog.
* **Status (`status.py`):** Reports PC online/offline, ECHO running/paused, current task, health summary, last heartbeat, and queue depth.
* **Privacy invariants:** The relay is invisible to the network (outbound only), REST control remains loopback-only, screenshots and dangerous actions require the owner, and no credential material is ever requested, stored in command text, or returned.
* **Surfaces:** REST `/api/v1/remote/*`, WebSocket `remote_*` events, and the Remote Relay modal (LINK, ACCESS, NOTIFICATIONS, AUDIT).

### 11. Notifications Subsystem (`echo/notifications`)
* **Role:** Dispatching alerts across appropriate delivery channels based on severity.
* **Channels:**
  * **Local Windows Toast Notifications:** Interactive native Windows toasts.
  * **Telegram Bot:** Delivered by the Stage 5 remote relay (`echo/remote`) using long polling, an explicit owner pairing, and the offline queue described above.
  * **SMTP Email:** Structured HTML summary digests for non-urgent reports.
  * **Escalation Matrix:** Configurable cascading escalation (Toast $\to$ Telegram $\to$ SMS/Call).

### 12. Scheduler & Autonomy (`echo/scheduler`)
* **Role:** Time-triggered task dispatching and recurring autonomous maintenance.
* **Features:**
  * Supports Cron syntax, interval timers, and one-shot delayed executions.
  * Timezone-aware scheduling with explicit daylight saving time policies.
  * Missed-run policies: `SKIP`, `RUN_ONCE`, or `BURST`.
  * Autonomy Tiers: Supervised (pauses for approval on T2+ actions) vs. Trusted (runs pre-approved routines within strict resource budgets).

### 13. Permissions & Security Engine (`echo/permissions`)
* **Role:** Central gatekeeper enforcing least privilege, capability scoping, and consent verification.
* **Mechanism:**
  * Granular scopes: `file:read`, `file:write`, `desktop:interact`, `browser:navigate`, `system:monitor`, `network:external`.
  * Risk tiers T0 to T4.
  * Time-bound, session-bound, and single-use grants.
  * Cryptographic argument hashing: user approval is bound to specific tool arguments. Replay with modified arguments is rejected.

### 14. User Interface (`frontend/` & `desktop/`)
* **Role:** Futuristic, high-density AI Command Center providing real-time visibility and control.
* **Tech:** React 18, TypeScript, Tailwind CSS, Lucide icons, Vite build toolchain, wrapped in an Electron desktop shell.
* **Visual Tone:** Obsidian dark theme (`#080B10`), neon cyan accents (`#00F0FF`), deep cobalt secondary glow (`#0070F3`), monospace telemetry type, clean glassmorphic panels, and animated status orbs.

### 15. Logging & Auditing (`echo/audit` & `echo/core/logging`)
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

-- 3. Memory (migration 4 rebuild) + FTS5 keyword index
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL CHECK(category IN (
        'fact', 'project', 'preference', 'context', 'task', 'conversation'
    )),
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    sensitivity TEXT DEFAULT 'normal' CHECK(sensitivity IN ('normal', 'high')),
    source TEXT NOT NULL DEFAULT 'user',
    tags TEXT NOT NULL DEFAULT '[]',
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    permission_granted INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    use_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    key,
    content,
    category,
    tags
);

-- Stage 6: directories the user explicitly approved for indexing/search.
CREATE TABLE IF NOT EXISTS approved_directories (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    label TEXT,
    recursive INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_indexed_at TEXT
);

-- One row per indexed file; content_text is capped and secret-redacted.
CREATE TABLE IF NOT EXISTS file_index (
    id TEXT PRIMARY KEY,
    directory_id TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    extension TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    modified_at REAL,
    created_at TEXT,
    content_hash TEXT,
    content_text TEXT,
    content_status TEXT NOT NULL DEFAULT 'not_indexed',
    metadata TEXT,
    indexed_at TEXT NOT NULL,
    error TEXT
);

-- File action audit. No delete action exists by design.
CREATE TABLE IF NOT EXISTS file_actions (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    source_path TEXT,
    target_path TEXT,
    status TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL
);

-- 5. Cryptographic Hash-Chained Audit Trail
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

-- 6. Monitoring Alerts & Event Feed (migration 2)
CREATE TABLE IF NOT EXISTS monitor_alerts (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'notice', 'warning', 'critical')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSON,
    status TEXT NOT NULL CHECK(status IN ('active', 'recovered', 'resolved')),
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_notified_at TEXT NOT NULL,
    acknowledged_at TEXT,
    recovered_at TEXT,
    resolved_at TEXT,
    escalation_level INTEGER NOT NULL DEFAULT 0
);

-- Only one active alert per dedupe key; repeats increment occurrences.
CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_alerts_active
    ON monitor_alerts(dedupe_key) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS monitor_events (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSON,
    alert_id TEXT,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

-- 7. Remote Relay (migration 3). Only hashes of pairing codes are stored.
CREATE TABLE IF NOT EXISTS remote_users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    display_name TEXT,
    role TEXT NOT NULL CHECK(role IN ('owner', 'allowed')),
    paired_at TEXT NOT NULL,
    last_seen_at TEXT,
    added_by TEXT NOT NULL DEFAULT 'pairing'
);

CREATE TABLE IF NOT EXISTS remote_pairing_codes (
    code_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    used_by INTEGER
);

CREATE TABLE IF NOT EXISTS remote_commands (
    id TEXT PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    command TEXT NOT NULL,
    args TEXT,
    status TEXT NOT NULL,
    response TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

-- Outbound queue; survives Telegram outages and collapses on reconnect.
CREATE TABLE IF NOT EXISTS remote_notifications (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'notice', 'warning', 'critical')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued', 'sending', 'sent', 'failed', 'expired', 'suppressed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    expires_at TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS remote_tasks (
    id TEXT PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('created', 'planning', 'in_progress', 'completed', 'failed', 'cancelled')),
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS remote_pending_actions (
    approval_id TEXT PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'denied', 'executed', 'expired')),
    result TEXT,
    task_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS remote_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 8. Scheduled Jobs
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
| **Internet / Network Offline** | External APIs & Telegram down | Local-first core functions identically: local models, desktop tools, and local alerts run normally. The remote relay stays outbound-only, alternates long-poll attempts with backoff, and queues eligible notifications in SQLite; on reconnect it expires stale rows, collapses duplicates, and sends one downtime summary instead of a backlog. |
| **PDF / OCR Packages Missing** | PDF text and image OCR unavailable | Indexing proceeds for supported formats; capability badges report `PDF OFF` / `OCR OFF`, and image rows still carry metadata when Pillow is installed. |
| **AI Provider Mock / Offline** | File summaries and chat reasoning are shallow | Summary returns an explicit mock response containing the extracted text rather than inventing facts; search, metadata, and all file actions remain local and unaffected. |
| **Database Lock / Contention** | SQLite concurrency conflict | SQLite WAL mode with 5000ms busy-timeout retry handles high concurrency smoothly. |

