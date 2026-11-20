# ECHO — Architecture Decision Records (ADRs)

> **Document Status:** Stage 0 Complete  
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

* **Status:** Accepted
* **Context:** Hands-free voice operation requires low latency, offline capability, and complete audio privacy.
* **Decision:** 
  * Wake Word: `openWakeWord` (zero network dependency).
  * VAD: `Silero VAD` (local ONNX runtime).
  * STT: `faster-whisper` (CTranslate2 backend).
  * TTS: `Piper` (neural local TTS) with Windows SAPI fallback.
* **Consequences:** Completely free and open-source. Voice interactions function without internet connectivity and without transmitting voice data to cloud providers.

