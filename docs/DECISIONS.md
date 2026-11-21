# ECHO — Architecture Decision Records (ADRs)

> **Document Status:** Stage 5 Remote Relay Implemented  
> **Last Updated:** November 2026

---

## ADR 001: Decoupled Daemon Process vs. Monolithic Electron Application

* **Status:** Accepted
* **Context:** A personal AI assistant must handle scheduled jobs, monitor system logs, and receive remote notifications (via Telegram) even when the user closes the main desktop window.
* **Decision:** We separate ECHO into two processes:
  1. A Python 3.12+ backend daemon running as an independent background service.
  2. An Electron + React client application that connects to the daemon over a loopback REST & WebSocket interface (`127.0.0.1`).
* **Consequences:** The UI can be closed and reopened without interrupting active agent tasks, monitoring watchers, or background cron automations. Daemon communications are secured via a per-session token.

---

## ADR 002: SQLite in WAL Mode for Single-Node Storage & FTS5

* **Status:** Accepted
* **Context:** We require local-first, zero-setup, zero-maintenance, ACID-compliant storage for messages, tasks, memories, and audit logs.
* **Decision:** Use SQLite 3 configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), synchronous normal, and foreign key enforcement. Full-text search is powered by SQLite's built-in `FTS5` engine with BM25 ranking.
* **Consequences:** Eliminates external database dependencies (e.g., PostgreSQL). Enables microsecond query times, high-concurrency readers, and portable single-file backups located in `%LOCALAPPDATA%\Echo\data\echo.db`.

---

## ADR 003: Playwright for Windows Browser Automation

* **Status:** Accepted
* **Context:** The agent needs to navigate websites, research information, and automate browser interactions reliably.
* **Decision:** Select Microsoft Playwright (Chromium engine) over Selenium or Puppeteer.
* **Consequences:** Playwright offers first-class async Python bindings, native accessibility tree extraction (`page.accessibility.snapshot()`), built-in auto-waiting, network route interception, and robust process isolation.

---

## ADR 004: Typed In-Process Event Bus with Bounded Queues

* **Status:** Accepted
* **Context:** Multiple subsystems (Monitoring, Scheduler, Voice, Agent) need to broadcast state changes to the WebSocket gateway and audit logger without tight coupling.
* **Decision:** Implement a typed async in-process Event Bus using Python `asyncio.Queue` with bounded capacity. Events follow a strict envelope structure (`event_id`, `timestamp`, `topic`, `payload`, `correlation_id`).
* **Consequences:** If the WebSocket client is slow or disconnected, bounded queues prevent memory leaks via backpressure drops with warning logs.

---

## ADR 005: Electron Security Gate & Hardening Policies

* **Status:** Accepted
* **Context:** Electron applications frequently suffer from Remote Code Execution (RCE) vulnerabilities if web content or untrusted data compromises the renderer.
* **Decision:** Enforce the following non-negotiable Electron security settings:
  1. `nodeIntegration: false` (strictly enforced in webPreferences).
  2. `contextIsolation: true` (strictly enforced).
  3. `sandbox: true` enabled on the renderer.
  4. Content Security Policy (CSP) restricting scripts to local self origin; no `unsafe-eval`.
  5. `webContents.setWindowOpenHandler` blocks all new window popups and external navigation unless explicitly routed to the user's default OS browser via `shell.openExternal`.
* **Consequences:** Even if malicious web content or an indirect prompt injection renders in the UI, it has zero access to Node.js or OS system APIs.

---

## ADR 006: Local Speech Stack (faster-whisper, Piper, openWakeWord)

* **Status:** Partially implemented — faster-whisper adopted; wake word and TTS engine changed by ADR 007.
* **Context:** Hands-free voice operation requires low latency, offline capability, and complete audio privacy.
* **Decision:** 
  * Wake Word: `openWakeWord` (zero network dependency).
  * VAD: `Silero VAD` (local ONNX runtime).
  * STT: `faster-whisper` (CTranslate2 backend).
  * TTS: `Piper` (neural local TTS) with Windows SAPI fallback.
* **Consequences:** Completely free and open-source. Voice interactions function without internet connectivity and without transmitting voice data to cloud providers.

---

## ADR 007: Stage 3 Local Voice Stack — Shared Whisper, Energy VAD, SAPI TTS

* **Status:** Accepted (Stage 3)
* **Context:** Stage 3 required a working offline wake word ("ECHO"), STT with partials, TTS, barge-in, and strict privacy with no cloud calls. The original plan (ADR 006) assumed openWakeWord, Silero VAD, and Piper, but none ships an "echo" wake model or voice out of the box; adding them would mean extra runtimes, model distribution, and install friction before the interaction loop could be validated.
* **Decision:**
  1. Use one shared local `faster-whisper` model (`tiny.en`, int8 CPU by default) for three jobs: keyword spotting on short energy-gated segments, partial transcripts, and final transcripts.
  2. Use an RMS energy gate with an adaptive noise floor for VAD and endpointing instead of Silero. It is deterministic, dependency-light, and adequate for near-field desktop microphones.
  3. Use `pyttsx3` over Windows SAPI for TTS instead of Piper. It is already present on Windows, supports voice/rate/volume, and needs no model download.
  4. Run the session in the daemon (`VoiceService` + `VoiceSession`), not in the browser. The UI is a control surface over REST/WebSocket; closing the window does not orphan a microphone stream.
  5. Keep raw audio in memory only and default `save_recordings` to false. Debug WAVs require explicit opt-in, have count-based retention, and can be purged from the UI/API.
* **Consequences:**
  * Fewer dependencies and no cloud keys; voice works fully offline after the first model download.
  * Trade-offs: wake-word false positives depend on sensitivity and microphone gain; `tiny.en` accuracy is modest; SAPI voice quality varies by machine.
  * The swap points are isolated (`echo/voice/wake_word.py`, `stt.py`, `tts.py`), so openWakeWord, Silero, or Piper can be adopted later without changing the session state machine or UI contract.
  * Privacy claims are testable: no audio files are written by default, and mute/reopen behavior is covered by tests.

---

## ADR 008: Stage 4 Monitoring — Daemon-Owned Engine, Persisted Alert Lifecycle, Concurrent Probes

* **Status:** Accepted (Stage 4)
* **Context:** Monitoring must run when the UI is closed, avoid saturating the CPU, survive restarts, and avoid alert fatigue. Some probes (temperature WMI/PowerShell, `wevtutil` Event Log reads, connectivity checks) are much slower than the 5-second snapshot cadence and would otherwise delay every dashboard update.
* **Decision:**
  1. Run the engine as a supervised asyncio task inside the daemon (`echo/monitoring/engine.py`). The UI never owns the sampling loop; it only consumes REST snapshots and WebSocket broadcasts.
  2. Keep a fast snapshot loop and spawn separate supervised tasks for slow probes. Network, temperature, and Windows Event Log checks run concurrently; a stalled probe cannot block snapshots, and a failed probe is retried on its own interval.
  3. Use threshold persistence (`sustained_seconds`) before raising an alert, plus a recovery hysteresis margin. This prevents single-sample spikes and flapping.
  4. Persist alerts and the event feed in SQLite. A partial unique index (`dedupe_key WHERE status = 'active'`) enforces one active alert per condition; repeats increment `occurrences`. Cooldowns suppress reminders; severity and time-based escalation handle unresolved alerts; recovery notifications are recorded.
  5. Expose profiles (`quiet`, `balanced`, `strict`) as coherent threshold/cadence presets, stored in `app_settings` with per-field overrides.
  6. Report unavailable data honestly. Temperature is `null` with a reason when no sensor bridge exists, and the UI displays "NO SENSOR" rather than inventing values.
* **Consequences:**
  * Monitoring continues across UI reloads and daemon restarts with alert state intact.
  * Snapshot latency stays stable even when Event Log or temperature probes are slow.
  * Alert history is queryable and filterable; tests cover dedupe, cooldown, escalation, recovery, persistence, and a real snapshot.
  * Trade-offs: Event Log polling is coarse (allowlisted IDs, lookback window) rather than a real-time subscription; temperature depends on optional hardware bridges; notification delivery is deferred to the Notifications stage.

---

## ADR 009: Stage 5 Remote Relay — Outbound Telegram Long Polling, Explicit Pairing, SQLite Delivery Queue

* **Status:** Accepted (Stage 5)
* **Context:** The owner needs to query ECHO and receive alerts from a phone without exposing desktop control to the internet. A webhook or inbound listener would require a public endpoint, TLS, and a new attack surface that contradicts the local-first model. Telegram also cannot be trusted to deliver in order during outages, so a naive send-and-forget path would either lose alerts or flood the owner after reconnecting.
* **Decision:**
  1. Use Telegram **long polling** (`getUpdates`) from the daemon over outbound HTTPS. No webhook, no inbound port, no public reverse proxy. The update offset is persisted in `remote_state` so restarts neither replay nor skip commands.
  2. Treat identity as an explicit, user-mediated grant. The bot token and numeric owner ID live in `app_settings`; the owner role is established only by entering a one-time 8-character pairing code whose SHA-256 hash is stored with a 5-minute expiry. Additional accounts are `allowed` and read-only.
  3. Reuse the existing safety stack instead of duplicating it. Remote actions go through `ToolRegistry` schema validation and `PermissionManager`; dangerous tools create pending approvals executed exactly once by either the desktop dialog or `/approve`. A separate `remote_pending_actions` row binds the approval to the requesting Telegram ID and arguments.
  4. Default-deny every remote surface: private chats only, owner-only screenshots, owner-only approvals and pause/resume, per-user rate limiting, pattern-blocked credential requests, and an audit row for accepted, rejected, rate-limited, and failed commands.
  5. Persist notifications in SQLite with severity TTLs, dedupe keys, and `next_attempt_at` backoff. On reconnect, expire stale rows, collapse duplicates, suppress overflow, and emit one downtime summary so recovery does not produce a flood.
  6. Keep the transport replaceable. `echo/remote` separates transport (`telegram.py`), policy (`service.py`), status (`status.py`), routing (`notifications.py`), and persistence (`store.py`), so a second channel can reuse pairing, approvals, audit, and the queue.
* **Consequences:**
  * No inbound network exposure: the relay is unreachable from the internet even while running.
  * Commands and approvals are attributable, rate-limited, replay-resistant, and auditable alongside desktop actions.
  * Alerts survive outages without loss or storms; queue state and relay health are visible in the UI.
  * Trade-offs: Telegram long polling adds a few seconds of command latency; only private chats are supported; live E2E delivery requires a real bot token; email/SMS/phone escalation remains future work.

---

## ADR 010: Stage 6 Memory & File Intelligence — Inspectable Memory, Approved Roots, No Deletion

* **Status:** Accepted (Stage 6)
* **Context:** The owner asked for memory covering personal preferences, project state, tasks, and conversations, plus local file search and actions. Memory that cannot be inspected or that silently captures secrets is a trust failure; file automation that can range across the disk or delete data is a safety failure. Both features also need to work without cloud services or optional heavy dependencies.
* **Decision:**
  1. Store all memory in one SQLite `memories` table with six categories (`fact`, `project`, `preference`, `context`, `task`, `conversation`) and an FTS5 keyword index. Record source, timestamps, confidence, tags, pin/archive state, and use counters so every recalled item is attributable. Do not ship embeddings; treat semantic search as an optional extension.
  2. Gate sensitive writes. Scan key and content for credentials and high-risk personal data after normalizing separators; refuse matches unless the caller explicitly grants permission. Mark permitted rows `sensitivity=high`, keep them out of automatic model context, and redact secrets before capturing task or conversation summaries.
  3. Capture automatically where it is useful: completed/failed tasks become `task` memory, and substantive conversations produce bounded rolling summaries. The memory explorer remains the single source of truth, with two-step delete/clear and JSON export.
  4. Make approved directories the only file boundary. Canonicalize every path and require containment by an enabled root for search, details, and all actions. Refuse drive roots and protected system paths. Removing a root revokes indexing only.
  5. Index on demand rather than with a watcher. Extract text with the standard library for text, CSV, DOCX, XLSX, and PPTX; enable PDF and OCR only when optional packages exist and report capability honestly. Skip credential files and redact extracted text.
  6. Forbid deletion at the API and engine level. Duplicate quarantine moves extra copies into `_ECHO_DUPLICATES` while keeping one copy. Organize, bulk rename, moves, and overwrites use a plan-and-confirm flow: above the configured threshold or on overwrite, return HTTP 409 with the full mapping until the caller confirms.
* **Consequences:**
  * Memory is auditable and falsifiable: the UI shows exactly what exists, and ECHO cannot claim to remember anything else.
  * Sensitive content requires an explicit, per-entry permission rather than a global setting.
  * File operations cannot escape approved roots and cannot delete data; bulk changes are previewed before execution.
  * Trade-offs: keyword search misses semantic paraphrases unless a vector extension is added; indexing is on-demand, so results can lag until a rescan; PDF/OCR depend on optional packages; duplicates are only detected within indexed roots.



