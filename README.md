# ECHO — Personal AI Assistant

> A local-first, Windows-native AI agent that can see, hear, remember, act — and ask before it does something that matters.

**Status:** Stage 6 — Memory & File Intelligence Operational & Verified.
ECHO now keeps inspectable personal, project, task, and conversation memory in SQLite, and can search and act on local files strictly inside directories the owner has approved. The memory explorer exposes every stored entry with provenance and a permission gate for sensitive content; the file panel indexes documents, finds duplicates, and moves or copies files without ever deleting them. Both surfaces reuse the existing daemon, audit, and permission model.

Earlier: Stage 5 delivered the outbound-only Telegram relay, Stage 4 daemon-owned system monitoring and the System Observatory, Stage 3 the offline voice system, and Stage 2 permissioned native Windows desktop control. All remain active in the running daemon.

---

## Why ECHO is not a chatbot

A chatbot answers. ECHO **operates**.

ECHO is designed as a persistent personal agent that runs on the user's Windows machine, understands intent, plans multi-step work, calls explicitly defined tools, verifies the result, remembers what matters, monitors the system, and reaches the user remotely when something needs attention.

It is built around one rule:

> **The model may propose actions. Only the runtime may perform them.**

---

## Implemented Desktop Capabilities (Stage 2)

ECHO's Windows desktop control substrate is built around a typed `ToolRegistry` with schema validation, permission gates, timeouts, and SQLite audit logging.

### 1. Screen Perception (`echo/tools/screen.py`)
- `screen.capture_desktop`: High-resolution full screen capture saved to `%LOCALAPPDATA%\Echo\screenshots` with real-time base64 thumbnail generation for AI vision.
- `screen.capture_region`: Bounded screenshot of specific screen coordinates and dimensions.
- **Safety Fallback:** Automatic degradation to headless/locked screen synthetic buffers if graphics context (`BitBlt`) is unavailable.

### 2. Window Management (`echo/tools/window.py`)
- `window.list`: Enumerates visible top-level Windows applications, handles (`HWND`), process IDs, and titles via native Win32 `EnumWindows`.
- `window.get_active`: Reads the current foreground window title, handle, and executable process.
- `window.switch`: Focuses and brings target window to foreground via `SetForegroundWindow`.
- `window.minimize`: Minimizes target window (`SW_MINIMIZE`).
- `window.maximize`: Maximizes target window (`SW_MAXIMIZE`).
- `window.restore`: Restores minimized or maximized window (`SW_RESTORE`).
- `window.close`: Safely sends `WM_CLOSE` to window (**APPROVAL REQUIRED**).

### 3. Mouse Interaction (`echo/tools/mouse.py`)
- `mouse.move`: Moves cursor to target $(x, y)$ coordinates with monitor bounds checking.
- `mouse.click`: Single click at current or target position (left, right, middle button).
- `mouse.double_click`: Double click target button.
- `mouse.right_click`: Context menu right click.
- `mouse.scroll`: Mouse wheel scrolling with directional step counts.

### 4. Keyboard Input (`echo/tools/keyboard.py`)
- `keyboard.type_text`: Text entry into active window with configurable character pacing.
- `keyboard.press_key`: Single key press (`enter`, `esc`, `tab`, `backspace`, etc.).
- `keyboard.hotkey`: Native key combinations (`ctrl+c`, `win+r`, `alt+tab`).

### 5. Application Lifecycle (`echo/tools/applications.py`)
- `application.list`: Lists safe approved shortcuts and running desktop GUI processes.
- `application.launch`: Launches approved Windows binaries (Notepad, Calculator, Paint, Explorer, Task Manager, Web Browser).
- `application.close`: Gracefully terminates application by PID or process name (**APPROVAL REQUIRED**).

### 6. Safe Filesystem Operations (`echo/tools/filesystem.py`)
- `filesystem.list_dir`: Lists directory contents with sizes and modification timestamps.
- `filesystem.search`: Recursive pattern search (`*.txt`, `report*`) with result limits.
- `filesystem.read_file`: Reads safe document text up to configured character limits.
- `filesystem.create_folder`: Safe directory creation.
- `filesystem.rename_file`: Safe file renaming.
- `filesystem.copy_file`: File copying with path safety verification.
- `filesystem.move_file`: Moves file to target path (**APPROVAL REQUIRED**).

### 7. Clipboard System (`echo/tools/clipboard.py`)
- `clipboard.read`: Reads active text content from Windows clipboard.
- `clipboard.write`: Sets clipboard contents.

### 8. Basic Windows Actions (`echo/tools/system_actions.py`)
- `system.open_settings`: Opens Windows Settings panel (`ms-settings:`).
- `system.open_explorer`: Opens File Explorer at target or default directory.
- `system.open_task_manager`: Opens Task Manager (`taskmgr.exe`).
- `system.open_browser`: Navigates default browser to validated URL.

---

## Implemented Voice Capabilities (Stage 3)

Voice runs as a daemon-owned session (`echo/voice`) that the UI starts explicitly; the browser is only a control surface. A dedicated worker thread captures audio and converts it to 16 kHz mono, and the same `ChatTurnService` used by text chat produces the reply, so spoken and typed turns share conversation history and behavior.

### 1. Speech-to-Text (`echo/voice/stt.py`, `echo/voice/vad.py`)
- Offline `faster-whisper` (`tiny.en`, int8 CPU by default), lazily loaded once and reused across turns.
- Energy-gated endpointing that adapts to the measured noise floor, ends an utterance after configurable silence, and hard-caps utterance length.
- Partial transcripts while the user is still speaking; a committed final transcript when the utterance ends.
- Recognition failures surface as explicit errors; empty captures are dropped instead of being sent to the model.
- Common short-audio hallucination artifacts are filtered out.

### 2. Text-to-Speech (`echo/voice/tts.py`)
- Offline Windows SAPI via `pyttsx3` on a dedicated thread.
- Voice selection, rate (80–350 wpm), and volume.
- Sentence-chunked queue so playback starts before the full reply is generated; abbreviation-aware chunking avoids mid-sentence stalls.
- Stop-speaking cancels the queue immediately; barge-in cancels playback when the microphone hears sustained speech.

### 3. Wake Word (`echo/voice/wake_word.py`)
- Default wake word `echo`, configurable with aliases (`hey echo`, `ok echo`, `eco`).
- Lightweight energy-gated keyword spotting: short speech segments are transcribed with the shared local Whisper model and fuzzy-matched against the wake word and aliases.
- Sensitivity control (0.0–1.0) trades false wakes against misses. A wake word followed by a command is handled in one utterance ("Echo, what's my CPU usage?").
- Configurable command window after a wake (default 12 s); when it expires ECHO returns to idle.

### 4. Conversation Modes (`echo/voice/session.py`)
- **Push-to-talk:** hold the pad (or the mic button) and release to transcribe; captured speech is always processed even if short.
- **Wake word:** idle until the wake word fires, then listen for the command.
- **Continuous:** keeps the conversation open for follow-ups until dismissed or the configurable timeout (default 30 s) expires.
- Every mode returns to idle. There is no invisible always-recording state.

### 5. Privacy Model
- Microphone state, capture state, and wake state are broadcast on every change and visible in the UI.
- Mute stops capture and reports `muted`; unmuting explicitly reopens the device.
- Raw audio lives in memory only and is discarded after transcription.
- Debug recordings are opt-in (`save_recordings`, default off), stored under `%LOCALAPPDATA%\Echo\voice\recordings`, and pruned to a configurable count.
- A purge action deletes recordings at any time.
- No cloud speech services are used.

### 6. Voice UI (`frontend/src/components/VoiceOrb.tsx`, `VoiceConsole.tsx`, `VoiceSettingsModal.tsx`)
- Animated state orb with calibration ticks and a level-reactive ring (idle, listening, processing, speaking, muted, error).
- Live input meter, partial transcript, status notice line, and mode selector (PUSH / WAKE / LIVE).
- Mute, stop-speaking, dismiss, and push-to-talk controls.
- Settings modal covering input device, STT model/language, TTS voice/speed/volume, wake word/sensitivity, timeouts, privacy, and diagnostics (installed packages, devices, latency, recordings).

### 7. Voice API
REST under `/api/v1/voice`: `status`, `settings`, `start`, `stop`, `mute`, `unmute`, `ptt/start`, `ptt/stop`, `stop-speaking`, `dismiss`, `conversation`, `test-speech`, `devices`, `voices`, `diagnostics`, `recordings`.

WebSocket commands: `voice_start`, `voice_stop`, `voice_status_request`, `voice_ptt_start`, `voice_ptt_stop`, `voice_stop_speaking`, `voice_mute`, `voice_unmute`, `voice_dismiss`, `voice_set_conversation`.

Events: `voice_status`, `voice_state`, `voice_session`, `voice_level`, `voice_transcript`, `voice_timing`, `voice_speaking`, `voice_speaking_text`, `voice_wake_word`, `voice_error`, `voice_engine`, `voice_conversation`, `voice_interrupted`, `voice_privacy`.

### Known Voice Limitations
- TTS uses installed Windows SAPI voices; quality depends on what is available (Piper is not wired yet).
- CPU Whisper `tiny.en` is fast but less accurate than larger models; the model is configurable.
- First run downloads the Whisper model once (roughly 75 MB) and may take about a minute; afterwards everything is offline.
- Wake word is local keyword spotting, not a dedicated openWakeWord model; phrasing and sensitivity need tuning per microphone.
- Barge-in uses sustained energy, so very noisy rooms may need a higher threshold.
- Voice extras are optional: install with `pip install -e ".[voice]"`.

---

## Implemented System Monitoring (Stage 4)

Monitoring is owned by the daemon (`echo/monitoring`) and keeps running when the UI is closed. The dashboard is a read/control surface: it subscribes to WebSocket snapshots and never produces synthetic data.

### 1. Engine (`echo/monitoring/engine.py`)
- Asyncio loop with a fast snapshot cadence (default 5 s) and slower, supervised probes for connectivity, temperature, and Windows Event Log reads so expensive queries never block the snapshot.
- Three profiles — `quiet`, `balanced`, `strict` — reset thresholds and cadences to a coherent preset; individual fields can then be overridden and are persisted in `app_settings`.
- Configurable per-metric switches, disk paths, probe targets, monitored applications, retention, cooldowns, escalation delay, and recovery margins.
- CPU use is bounded by design: `psutil.cpu_percent(interval=None)` is primed once, network rates come from counters, and event logs are read incrementally.

### 2. Collectors (`echo/monitoring/collectors.py`)
- **CPU / RAM / swap:** usage, core counts, clock, used/available memory, top processes by RSS.
- **Storage:** every fixed drive with total/used/free GB and percentage.
- **Battery:** percentage, plugged state, seconds remaining (when exposed).
- **Network:** down/up rates from interface counters, plus reachability/latency against configurable `host:port` targets.
- **Thermal:** optional sensor bridge (LibreHardwareMonitor / OpenHardwareMonitor WMI, then ACPI thermal zones). When no sensor is exposed the dashboard says so; it never fabricates a temperature.
- **Applications:** selected processes, crash/absence detection, and Win32 hung-window detection (`IsHungAppWindow`).
- **Windows Events:** `wevtutil` queries over System (allowlisted event IDs) and Application Error/Hang channels, parsed from XML with a lookback window and per-log cap. Informational events are downgraded so they do not masquerade as warnings.

### 3. Alert Lifecycle (`echo/monitoring/alerting.py`, `store.py`)
- Four severities: `info`, `notice`, `warning`, `critical`.
- Threshold persistence: a condition must hold for its sustained window (for example, memory above 90% for two minutes) before alerting.
- Deduplication by stable key with a partial unique index on active alerts; repeats increment occurrences instead of creating rows.
- Cooldown-limited reminders, immediate severity escalation, time-based escalation for unresolved alerts, acknowledgement, manual resolution, and automatic recovery once the value clears the hysteresis margin.
- Recovery and acknowledgement events are recorded; active-alert state survives daemon restarts.

### 4. Persistence
Two SQLite tables created by migration 2: `monitor_alerts` (lifecycle, severity, occurrences, timestamps) and `monitor_events` (immutable feed of alerts, acknowledgements, recoveries, and Windows events). Old records are purged by retention days.

### 5. API & WebSocket
- REST under `/api/v1/monitoring`: `status`, `snapshot`, `settings` (GET/PUT), `alerts`, `events`, `start`, `stop`, and `alerts/{id}/acknowledge|resolve`.
- Events: `monitor_status`, `monitor_snapshot`, `monitor_alert`, `monitor_recovered`, `monitor_event`, `monitor_error`.
- WebSocket commands: `monitor_status_request`, `monitor_start`, `monitor_stop`, `monitor_acknowledge`, `monitor_resolve`.

### 6. System Observatory UI (`frontend/src/components/SystemDashboard.tsx`)
- **Overview:** CPU, memory, storage, network, battery, and thermal tiles with live sparklines; per-volume usage; uptime, boot time, process count, swap, and top memory consumers; signal availability; active alerts.
- **Alerts:** filter by status and severity, inspect occurrences and first-seen time, acknowledge or resolve.
- **Event Feed:** filterable history of alerts, acknowledgements, recoveries, and Windows events.
- **Config:** profile selection, cadence, feature switches, thresholds, probe targets, monitored apps, disk paths, and save/reset.
- Sidebar badge reflects active alerts and severity; the dashboard can start and stop the engine directly.

### Known Monitoring Limitations
- Temperature requires a hardware bridge (LibreHardwareMonitor/OpenHardwareMonitor) or ACPI exposure; many laptops expose none, and ECHO reports that honestly.
- Hung-window detection relies on Win32 heuristics and only covers visible top-level windows.
- Windows Event Log access depends on the account's read permissions; unavailable logs are surfaced in the UI.
- Notification delivery (toast, Telegram, email), quiet hours, and digest batching are not part of Stage 4; alerts live in the daemon and UI.

---

## Implemented Remote Connection (Stage 5)

The remote relay (`echo/remote`) is daemon-owned and outbound-only: it calls Telegram `getUpdates` with long polling, persists the offset, and never listens on an inbound port or exposes a desktop-control server to the network. Telegram is the first channel; the transport, pairing, queue, and audit layers are channel-agnostic.

### 1. Telegram Transport & Pairing
- Bot token stored in `app_settings`, masked in every API response (`CONFIGURED …9fQ2`). Owner ID must be numeric; only that Telegram account holds the `owner` role.
- **Explicit pairing:** the desktop generates a short-lived one-time code (8 characters, unambiguous alphabet, 5-minute TTL). The code is never stored in clear text — only its SHA-256 hash is persisted. Sending `/pair CODE` transfers owner status once; reused or expired codes are rejected.
- **Allowed users:** additional Telegram accounts can be added by ID. They are read-only (`/status`, `/health`, `/events`, `/tasks`) and never receive screenshots or execute tools.
- **Connection status & recovery:** relay state (`LINKED`, `OFFLINE`, `PAUSED`), last poll, heartbeat, poll attempts, uptime, and last error are persisted and exposed in the UI. Polling backs off and reconnects automatically; the `getUpdates` offset prevents replayed commands.
- **Privacy:** only private chats are accepted; group messages are ignored and audited. REST control stays on `127.0.0.1`.

### 2. Remote Commands
- Owner: `/ask <question>`, `/task <goal>`, `/status`, `/health`, `/events`, `/tasks`, `/screenshot`, `/open <app>`, `/approve <id>`, `/deny <id>`, `/pause`, `/resume`, `/pair <code>`, `/whoami`, `/help`.
- Allowed users: the four read-only commands above.
- `/status` reports PC online/offline, ECHO running/stopped or paused, current task, system health (CPU/RAM/disk), last heartbeat, and queue depth.
- `/ask` runs a normal chat turn and escapes HTML before sending. `/task` mirrors into the local `tasks` table so remote work is visible in the desktop UI.
- Free text from the owner is handled as a question; obvious task intents ("check whether my computer is online", "tell me available storage") map to structured status/storage commands.
- Commands are rejected while ECHO is paused except `/status`, `/health`, `/resume`, `/help`, and `/start`.

### 3. Remote Tasks & Approvals
- Remote goals are persisted in `remote_tasks` with status (`created`, `planning`, `in_progress`, `completed`, `failed`, `cancelled`), result, and error.
- Dangerous actions (launching an application, capturing a screenshot on behalf of another request) create a pending approval row bound to the requesting Telegram ID, tool name, and arguments.
- `/approve <id>` and `/deny <id>` are owner-only; the desktop approval dialog and the Telegram command both execute exactly once. Approvals expire and cannot be replayed with modified arguments.

### 4. Notifications & Offline Queue
- Events routed to the owner: critical alerts, selected warnings, completed/failed tasks, approval requests, PC online/offline, and filtered monitoring events.
- Routing policy is configurable: per-category toggles, minimum event severity, event categories, screenshot delivery, and queue limits.
- Notifications persist in SQLite (`remote_notifications`) with severity-based TTLs, dedupe keys, exponential backoff, and stuck-`sending` recovery.
- If Telegram is unreachable, rows stay queued; on reconnect, stale entries expire, duplicates collapse, overflow is suppressed, and a single downtime summary replaces the backlog so the user does not receive a flood.

### 5. Screenshots
- `/screenshot` is owner-only and requires the relay plus a paired owner identity.
- Captures go through the existing `screen.capture_desktop` tool; images are sent as Telegram photos and fall back to documents only above the 9 MB limit.
- Allowed users and unauthorized chats never receive screen captures.

### 6. Command Security
- Unauthorized Telegram IDs are rejected before dispatch and audited as `rejected`.
- Every command writes a `remote_commands` row (actor, command, arguments, status, response/error, timestamps), including rate-limited and rejected attempts.
- Per-user rate limiting (20 commands/minute) blocks bursts and reports the limit to the sender.
- Credential requests are hard-blocked in `/ask`, `/task`, free text, and remote task goals. Patterns for passwords, credentials, API/private keys, secrets, seed phrases, recovery codes, 2FA, and OTPs are refused before any model call.
- Dangerous tools remain `APPROVAL_REQUIRED`; the remote channel cannot bypass the tool registry, schema validation, or the permission manager.

### 7. Remote Relay UI (`frontend/src/components/RemoteRelay.tsx`)
- `LINK`: credentials (masked token, owner ID), relay control and transport stats, pairing-code generation with countdown, pending-approval count, and the privacy posture (0 inbound ports, outbound long poll, owner-only screenshots, credentials blocked, approvals required).
- `ACCESS`: allowed-user management, pending dangerous actions, owner identity, and the access rules.
- `NOTIFICATIONS`: routing toggles, minimum severity, event categories, screenshot delivery, queue statistics, notification table with retry, and offline behavior.
- `AUDIT`: remote command log and remote task history.
- A sidebar entry shows relay state and queued-notification count.

### Known Remote Limitations
- Only private Telegram chats are supported; webhooks and public endpoints are intentionally absent.
- `/ask` uses the configured brain provider; with no model reachable it returns the same honest provider error as desktop chat.
- Screenshot delivery depends on Telegram's photo size limits and the local capture stack.
- Group chats, inbox-style attachments, SMS, and phone-call escalation remain future work.
- Live Telegram end-to-end delivery requires a real bot token and owner ID; the test suite exercises the transport with a fake client.

---

## Implemented Memory & File Intelligence (Stage 6)

### 1. Memory Store (`echo/memory/store.py`)
- **Categories:** `fact`, `project`, `preference`, `context`, `task`, and `conversation` cover personal preferences, project state, completed/failed tasks, and rolling conversation context.
- **Provenance:** Every entry keeps source (`user`, `task`, `conversation`), timestamps, confidence, tags, pin/archive flags, last-used time, and use count. Nothing is recalled unless it exists in this table.
- **Automatic capture:** Finished tasks are recorded as task memory; conversations record a bounded rolling summary when enough substantive turns accumulate.
- **Search:** SQLite FTS5 over key, content, category, and tags; prefix tokens make partial queries work. Semantic/vector search and RRF remain an optional extension, not a dependency.
- **Sensitivity:** Credential and high-risk personal patterns are detected after normalizing `_`/`-`. Matching writes are refused unless the user explicitly grants permission; permitted rows stay `sensitivity=high` and are excluded from model context. Captured task/conversation text is redacted first.
- **User control:** View, search, edit, pin, archive/restore, delete (two-step), clear (two-step), and JSON export. Clearing requires `{"confirm": true}`.

### 2. Memory API (`echo/api/routes/memory.py`)
`GET/POST /api/v1/memory`, `GET /api/v1/memory/stats`, `GET /api/v1/memory/export`, `GET/PATCH/DELETE /api/v1/memory/{id}`, and `POST /api/v1/memory/clear`. Refused sensitive writes return HTTP 422 with an explanation.

### 3. File Engine (`echo/files/`)
- **Approved roots only:** Search and actions are canonicalized and containment-checked against enabled rows in `approved_directories`. Drive roots and protected system paths are refused. Removing a root revokes indexing permission but never touches disk.
- **Indexing:** Explicit index runs record path, name, extension, category, size, timestamps, SHA-256, extracted text, and metadata. Credential files (`.env`, `.pem`, keys, keystores, `credentials.json`) are skipped; extracted text is redacted.
- **Extraction:** Text/code, CSV/TSV, DOCX, XLSX, and PPTX work with the standard library. PDF text (`pypdf`) and OCR (`pytesseract`) activate only when installed; capability reporting states what is available. Images expose metadata through Pillow when present.
- **Search and reports:** Filename, path, or content queries with category, extension, size, date, sort, and root filters; duplicate groups by content hash and size; largest files; category totals.
- **Actions:** Open, rename, copy, move, organize by type, bulk rename, summarize, and duplicate quarantine. Every action is written to `file_actions`.
- **No deletion:** There is no delete endpoint, tool, or action. Quarantine moves extra copies into `_ECHO_DUPLICATES` and keeps one copy in place.
- **Confirmations:** Moving/renaming more files than the configured threshold, and any overwrite, returns HTTP 409 with a structured plan; the UI previews every source/target pair and requires explicit confirmation.

### 4. File API (`echo/api/routes/files.py`)
Status, directories, index, search, stats, categories, duplicates, large files, details, activity, and settings under `/api/v1/files`, plus action endpoints for open, rename, copy, move, organize, bulk-rename, duplicate quarantine, and summarize.

### 5. UI
- **Memory Explorer** (`frontend/src/components/MemoryModal.tsx`): header stats, class rail with counts, archived toggle, FTS search, create/edit form (category, key, content, confidence, tags, pin, explicit sensitive permission), provenance cards, two-step delete/clear, and JSON export.
- **File Intelligence** (`frontend/src/components/FileIntelligence.tsx`): SEARCH, LIBRARY, DUPLICATES, DIRECTORIES, and ACTIVITY tabs; filters; snippet results; file inspector with hash, preview, Open, Summarize, Rename, and Copy/Move; category and largest-file views; organize and bulk-rename previews; duplicate groups with quarantine confirmation; approved-root management and indexing settings; local audit feed.

### Known Stage 6 Limitations
- Search is keyword/FTS-based; no embeddings are required or shipped. Semantic search is an optional extension.
- PDF and OCR require optional packages and report their absence rather than silently failing.
- Summaries use the configured brain provider; with the mock provider the response is explicitly a mock containing the extracted text, not invented analysis.
- Indexing is on-demand, not a filesystem watcher. Duplicate detection only considers indexed files.
- File "open" uses the OS default application and is limited to approved roots; executables are refused.

---

## Security & Permission Model

| Permission Level | Description | Behavior |
|---|---|---|
| **AUTOMATIC** | Non-destructive queries, screen captures, file reads, window listing, basic typing/clicks | Executes immediately within sandbox timeout |
| **APPROVAL_REQUIRED** | Window closing, process termination, file movement, destructive modifications | Halts execution, registers pending approval request, and displays visual confirmation dialog |

### Security Invariants Enforced:
1. **Path Traversal Prevention:** Target paths are resolved and checked. Access to `Windows\System32\config`, `SAM`, credential vaults, `.ssh`, `.aws`, `.env`, and private keys is hard-blocked.
2. **No Arbitrary Command Execution:** LLM is strictly prohibited from generating raw shell/PowerShell strings. Only registered, typed Pydantic tools can execute.
3. **Audit Trail:** Every tool invocation, whether automatic or approved, is logged to `action_logs` with timestamps, actor, parameters, and status.

---

## Control Panel & UI Features

- **ECHO Control Panel Modal:**
  - Real-time catalog of all registered tools with schema specifications and permission indicators.
  - Interactive "Execute" tool launcher for manual testing and verification.
  - Active foreground window inspector with instant screenshot capture and image preview.
  - Pending approval queue with parameter inspection.
  - Chronological action log feed.
- **Visual Approval Dialog:**
  - High-visibility amber security dialog showing exact tool parameters before any restricted operation can proceed.

---

## Development & Test Commands

### 1. Run the Full Test Suite
```powershell
.\scripts\test.ps1
```
Or directly with pytest:
```powershell
.\.venv\Scripts\pytest -o pythonpath=. -v
```
*(109 backend tests pass across core, memory, file intelligence, brain, desktop tools, voice, monitoring, and the remote relay. One non-failing deprecation warning comes from the third-party `mss` screen-capture library.)*

### 2. Launch Development Environment
```powershell
.\scripts\dev.ps1
```
Open **`http://127.0.0.1:5173`**. Use **Desktop Control** in the left sidebar for the tool catalog and approvals, **System Monitor** for the live observatory and alert history, **Remote Relay** to configure the Telegram bot, pair the owner, review queued notifications, and audit remote commands, **File Intelligence** to approve roots and search/act on local files, **Persistent Memory** to inspect or edit what ECHO remembers, and the microphone button in the composer to start the Voice Console.

### 3. Voice Extras
Voice ships as an optional dependency group so the core daemon runs without audio libraries:
```powershell
.\.venv\Scripts\pip install -e ".[voice]"
```
The first voice start downloads the Whisper model once. After that, STT and TTS are fully offline. Windows SAPI provides the installed system voices.

---

## Roadmap Summary

The table below reflects the order in which stages were actually built. `docs/ROADMAP.md` retains the original long-range numbering (memory was originally Stage 3, voice Stage 9, monitoring Stage 10, and the remote relay Stage 12).

| Stage | Theme | Status |
|---|---|---|
| 0 | Architecture, security model, UI direction, roadmap | ✅ Complete |
| 1 | Foundation: ECHO Core (Daemon, SQLite WAL, UI Shell, Memory, Brain) | ✅ Complete |
| 2 | Desktop Control: Tool Registry, Win32 API, Screen, Mouse, Keyboard, Approvals | ✅ Complete |
| 3 | Voice Interaction: Offline STT/TTS, Wake Word, Push-to-Talk & Continuous Modes | ✅ Complete |
| 4 | System Monitoring: Hardware Telemetry, Event Log, Alert Lifecycle & Observatory | ✅ Complete |
| 5 | Remote Connection: Telegram Relay, Pairing, Remote Commands, Offline Notifications | ✅ Complete |
| 6 | Memory & File Intelligence: Memory Explorer, Approved-Root Search, Extraction, Duplicate Quarantine, Safe Actions | ✅ Complete |
| 7 | Tools, Permissions (T0–T4) & Hash-Chained Audit Trails | Planned |
| 8 | Agent Planner & Verification Runtime State Machine | Planned |
| 9 | File Intelligence & Safe Operations | ✅ Delivered in Stage 6 |
| 10 | Advanced Desktop Control (OCR & Accessibility Trees) | Planned |
| 11 | Browser Automation (Playwright Sandboxing) | Planned |
| 12 | Notifications: Windows Toast & Email Delivery | Planned |
| 13 | Scheduler & Autonomous Routines | Planned |
| 14 | Remote Escalation Calls | Planned |
| 15 | Desktop Packaging, Hardening & Release | Planned |

