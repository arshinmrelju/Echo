# ECHO — Development Roadmap

This roadmap is deliberately staged. Each stage must be independently runnable, tested, documented, and useful before the next begins. Later stages may be re-ordered only when a dependency is preserved.

> **Implementation note:** the build order diverged from the numbering below. Desktop Control shipped as build Stage 2, Voice as Stage 3, System Monitoring as Stage 4, and the Remote Relay (M12) as Stage 5 (this document still calls Monitoring "S10" and Voice "M9"). The original long-range numbering is preserved so dependency references stay stable; `README.md` lists the shipped order.

**Guiding rule:** build the safety and observability layers *before* granting the agent side effects.

---

## Dependency graph

```text
M0 Planning
 └─ M1 Foundation & Shell
     ├─ M2 Brain & Conversation
     │   ├─ M3 Memory
     │   ├─ M9 Voice (can start after M2)
     │   └─ M10 Monitoring & Notifications (needs M1 only, but benefits from M2)
     ├─ M4 Tools, Permissions & Audit
     │   └─ M5 Agent Runtime
     │       ├─ M6 File Intelligence
     │       ├─ M7 Desktop Control
     │       ├─ M8 Browser Automation
     │       └─ M11 Scheduler & Autonomy
     │           └─ M12 Remote Contact & Calls
     └─ M13 Hardening & Packaging (after M6–M12)
```

Hard dependencies:

- **M4 before any side-effecting tool.**
- **M5 before file writes, desktop input, browser interaction, or autonomous scheduling.**
- **M12 after M4 and M11** so remote approvals and unattended tasks share one permission model.
- **M13 last**, but its Electron security checklist is reviewed at M1 and re-checked at M8.

---

## Definition of done (every stage)

A stage is complete only when all of the following are true:

1. The requested functionality works end-to-end, not as a mock.
2. Backend tests pass; new behavior has unit and/or integration coverage.
3. Frontend tests pass for new UI behavior.
4. Linting and type checking pass (`ruff`, `mypy`, `eslint`, `tsc`).
5. Errors are handled and surfaced honestly; no fake success states.
6. Security-sensitive changes are covered by a test or a documented manual check.
7. Documentation is updated, including known limitations.
8. No secrets, generated data, or machine-specific paths are committed.
9. The stage report lists what works, what does not, and what was deferred.

---

## Stage 0 — Architecture & Planning ✅

**Goal:** Establish a coherent, secure, buildable design before writing application code.

**Deliverables**

- Product vision, principles, and non-goals.
- Module map with responsibilities and boundaries.
- Runtime/process model and data architecture.
- Tool contract and permission model.
- Threat model and security invariants.
- UI design system and screen inventory.
- Decision records, including the Electron packaging gate.
- Staged roadmap with testable acceptance criteria.

**Acceptance criteria**

- All 14 required modules have a defined home and interface.
- Every high-risk capability has an approval and verification path.
- The first executable stage (M1) has an unambiguous scope.
- No application code is created prematurely.

**Tests:** Not applicable; documentation-only stage. Links and document consistency are reviewed manually.

---

## Stage 1 — Foundation & Shell ✅

**Goal:** A runnable, observable skeleton with a premium UI shell and no AI behavior yet.

**Scope**

- Python package, `pyproject.toml`, dependency groups, `ruff`, `mypy`, `pytest`.
- Configuration via `pydantic-settings`; `.env.example`; no secrets in source.
- Data directory resolution under `%LOCALAPPDATA%\Echo` with overrides.
- SQLite connection layer, WAL mode, migration runner, initial schema.
- Typed in-process event bus with bounded queues and event envelope.
- Kernel lifecycle: service registry, startup ordering, health checks, graceful shutdown.
- FastAPI app bound to `127.0.0.1` with per-run token auth, Host/Origin validation, and CORS locked to the UI.
- Endpoints: `/healthz`, `/readyz`, `/api/v1/system/status`, `/api/v1/ws-ticket`.
- WebSocket gateway with heartbeat, sequence numbers, and reconnect/resume support.
- Structured JSON logging with correlation IDs and redaction hooks.
- React + TypeScript + Vite + Tailwind frontend shell with design tokens and app layout.
- Live daemon status, connection indicator, navigation rail, command palette skeleton.
- Electron development shell with hardened defaults: `contextIsolation`, `sandbox`, `nodeIntegration: false`, strict CSP, navigation/window-open denial.
- Scripts for dev, test, lint, and typecheck.
- Initial README quickstart and architecture status update.

**Explicitly out of scope:** any LLM call, chat persistence, tools, permissions UI, voice, monitoring.

**Acceptance criteria**

- `.\scripts\dev.ps1` starts the daemon and UI.
- `/healthz` returns healthy; the UI shows “connected” from a real WebSocket heartbeat.
- Killing and restarting the daemon reconnects the UI automatically.
- Unauthenticated REST and WebSocket requests are rejected.
- Renderer has no Node.js access; external navigation is blocked.
- Database migrations apply cleanly to an empty file and are idempotent.
- Backend and frontend test suites pass; type checks are clean.
- No API keys or machine-specific absolute paths exist in tracked files.

**Primary risks:** over-engineering the kernel; Electron/Python process coordination; Windows path handling.

---

## Stage 2 — AI Brain & Conversation ✅

**Goal:** Real streaming conversation against a local or OpenAI-compatible model, with honest failure states.

**Scope**

- Provider abstraction: `ModelProvider` interface with capabilities and health.
- Providers: Ollama, generic OpenAI-compatible (LM Studio, vLLM, cloud), and a deterministic fake provider for tests.
- Model discovery, selection, and per-conversation overrides.
- Prompt assembly: system policy, persona, memory placeholders (not yet populated), tool schema slot (empty).
- Streaming over WebSocket with cancellation and backpressure.
- Conversation and message persistence; resume after restart.
- Token/latency accounting; context-window guard and truncation strategy.
- Settings UI for endpoint, model, temperature, and API key (stored in Credential Manager).
- Error taxonomy: unreachable provider, auth failure, rate limit, context overflow, cancelled.
- Offline behavior: clear diagnostics and a local-model setup guide.

**Explicitly out of scope:** tools, agent loop, long-term memory, voice.

**Acceptance criteria**

- A scripted fake provider proves streaming, cancellation, persistence, and reconnect.
- Cancelling a response stops generation within 500 ms and persists a `cancelled` state.
- API keys never appear in the database, logs, API responses, or frontend storage.
- A conversation survives a daemon restart and renders identically.
- Provider failure produces an actionable error card, not a silent hang.
- Backend tests cover provider fallback and malformed stream chunks.

**Primary risks:** inconsistent provider APIs; streaming cancellation semantics; context truncation quality.

---

## Stage 3 — Persistent Memory

**Goal:** Memory that improves answers without becoming an unreadable data dump.

**Scope**

- Memory kinds: working (session/task), episodic (events and summaries), semantic (facts/preferences), procedural (declarative workflows, later).
- SQLite schema with scope, source, confidence, importance, sensitivity, timestamps, and expiry.
- FTS5 keyword retrieval plus optional local embeddings (Ollama or ONNX/fastembed).
- Hybrid retrieval with reciprocal rank fusion, recency decay, importance, and token budgeting.
- Explicit “remember this”, “forget this”, and “why do you remember this?” flows.
- Post-conversation extraction with a review queue for sensitive or low-confidence facts.
- Deduplication and contradiction handling (supersede, don’t silently overwrite).
- Memory explorer UI: search, filter by kind/scope, edit, delete, export.
- Consolidation job: summarize old episodes, expire low-value items, enforce retention limits.

**Explicitly out of scope:** cross-device sync, cloud vector databases.

**Acceptance criteria**

- Store, retrieve, update, and forget flows work from UI and API.
- Retrieval returns scoped results only; a project-scoped memory never leaks into another scope.
- Duplicate facts are merged or superseded with provenance.
- Retrieval p95 < 150 ms for 10,000 memories on a typical development machine.
- Embedding provider outage degrades to FTS-only with a visible notice.
- Export produces a human-readable archive; deletion is verifiable.

**Primary risks:** memory poisoning, privacy leaks, retrieval noise, unbounded growth.

---

## Stage 4 — Tools, Permissions & Audit

**Goal:** A trustworthy execution substrate. This is the security keystone of the project.

**Scope**

- Tool contract: name, version, description, Pydantic args schema, risk tier, scopes, side effects, idempotency, timeout.
- Tool registry with JSON Schema generation for the model.
- Invocation pipeline: validate → authorize → preflight → approve (if required) → execute with timeout → verify → audit.
- Risk tiers T0–T4 and capability scopes (files, desktop, browser, network, notifications, system).
- Permission engine: deny-by-default for T2+, session grants, time-bound grants, use limits, revocation.
- Approval UI bound to an argument hash; changed arguments require re-approval.
- Emergency stop: global hotkey and UI control that cancels agents and revokes session grants.
- Append-only audit log with hash chaining, redaction, rotation, and a verification command.
- Built-in low-risk tools: current time, system info, read-only file inspection inside an allowlisted root, notes.
- Tool contract conformance test suite.
- Audit viewer UI with filters and correlation traces.

**Explicitly out of scope:** desktop input, browser control, file mutation, scheduling.

**Acceptance criteria**

- Invalid arguments are rejected before execution with a typed error.
- A T2 tool cannot run without an approval record; approval replay is rejected.
- Path traversal, symlink escape, UNC escape, and reserved-device paths are blocked in tests.
- Every invocation produces an audit record; tampering breaks verification.
- Emergency stop cancels a running invocation within 1 second and leaves a clear audit trail.
- Tool failures are reported as failures; verification cannot be skipped.
- No tool can be invoked by name unless it is registered and permitted.

**Primary risks:** approval fatigue, TOCTOU, scope design mistakes, audit log leakage.

---

## Stage 5 — Agent Runtime

**Goal:** Multi-step, cancellable, verifiable task execution.

**Scope**

- Task state machine: created → planning → awaiting approval → executing → observing → verifying → completed/failed/cancelled/paused.
- Planner/executor loop with structured tool calls, bounded steps, wall-clock, token, and cost budgets.
- Observation handling: truncation, provenance labels, untrusted-content fencing.
- Verification gate: the agent cannot claim success when verification failed.
- Retry and re-plan policy with limits and explicit failure reasons.
- Checkpointing after every step; resume after restart; idempotency keys for side effects.
- Task timeline UI: plan, tool cards, arguments, evidence, approvals, errors, cancellation.
- Dry-run mode for plans that mutate state.
- Prompt-injection test fixtures: malicious file/browser content attempting to trigger tools.
- Agent evaluation harness with scripted scenarios.

**Explicitly out of scope:** real file/desktop/browser tools (added next), autonomous triggers.

**Acceptance criteria**

- A scripted multi-step task completes with a verified result.
- Step, time, and token budgets stop runaway loops with a clear reason.
- Approval pause and resume work across a daemon restart.
- Cancellation is cooperative and prompt; no orphaned tool calls.
- Malicious content cannot cause an unapproved T2+ action in the injection suite.
- Task records include enough evidence to reconstruct what happened.

**Primary risks:** loop divergence, prompt injection, misleading model summaries, state-machine complexity.

---

## Stage 6 — File Intelligence

**Goal:** Make the user’s files searchable and safely operable.

**Scope**

- Configurable indexed roots with explicit exclusions (system, secrets, credential stores).
- Incremental indexing via filesystem watcher plus periodic reconciliation.
- Text extraction: plain text, Markdown, PDF, DOCX, XLSX, PPTX, HTML, and images via OCR (optional).
- Chunking, metadata, FTS5, optional embeddings, and hybrid search.
- File tools: search, read, summarize, copy, move, rename, create folder, trash (never permanent delete by default).
- Preview and diff before mutation; approval for moves/deletes outside a designated workspace.
- Duplicate detection and storage insights.
- Files UI: search, filters, preview, indexed roots, reindex controls.

**Explicitly out of scope:** cloud drives, network shares by default, permanent deletion.

**Acceptance criteria**

- 1,000 mixed files index without blocking the UI; progress is visible.
- Incremental updates reflect create/modify/delete within 5 seconds.
- Search returns relevant results with snippets and source paths.
- Mutations are verified by stat/hash and are reversible via the Recycle Bin.
- Symlinks, junctions, and paths outside allowed roots are rejected.
- Indexing excludes configured sensitive directories and never reads credential stores.

**Primary risks:** parser vulnerabilities, huge files, OCR cost, accidental data exposure.

---

## Stage 7 — Desktop Control

**Goal:** Reliable, observable Windows interaction with strong guardrails.

**Scope**

- Window enumeration, focus, minimize/maximize, and app launch via explicit executable allowlist.
- UI Automation first (pywinauto/uiautomation); coordinate input only as a fallback.
- Screenshot capture (mss) with region and monitor awareness; OCR via Windows OCR or Tesseract.
- Keyboard and mouse tools with argument validation, screen-bounds checks, and rate limits.
- Approval rules for typing, clicking, and interacting with sensitive apps (password managers, banking, terminals, UAC).
- Failsafe corner abort, global stop hotkey, and per-task input lock.
- Before/after screenshots and UI state as verification evidence.
- Desktop UI: live screen preview, action log, approval prompt, input lock indicator.

**Explicitly out of scope:** kernel-level drivers, anti-cheat bypass, unattended UAC elevation.

**Acceptance criteria**

- List/focus Notepad and type verified text in an integration test.
- Click targets are validated against monitor bounds and DPI scaling.
- Sensitive-app rules block or require approval in tests.
- Failsafe and hotkey abort stop input immediately.
- Every action has before/after evidence where feasible.
- No tool can execute arbitrary shell commands.

**Primary risks:** fragile UI automation, DPI/multi-monitor issues, destructive misclicks, accessibility regressions.

---

## Stage 8 — Browser Automation

**Goal:** Useful web tasks without handing the model a blank check.

**Scope**

- Playwright Chromium with a persistent, user-visible profile; no stealth/anti-detection features.
- Domain allowlist and per-task navigation scope; block `file:`, `javascript:`, and private-network targets by default.
- Accessibility-tree snapshots with stable element refs; screenshot fallback.
- Actions: navigate, read, click, fill, select, scroll, wait, download (sandboxed), extract structured data.
- Approval for form submission, purchases, messages, account changes, and downloads outside the sandbox.
- Credential use through Windows Credential Manager; secrets never enter model context.
- Session isolation per task; explicit close and cleanup.
- Browser UI: live view, action timeline, domain indicator, take-over control.

**Explicitly out of scope:** CAPTCHA solving, stealth evasion, mass scraping, cookie exfiltration.

**Acceptance criteria**

- Navigate and extract content from an allowlisted test page.
- Denied domains and private-network SSRF targets are blocked in tests.
- A form fill + submit requires approval and is verified by page state.
- Credentials are injected at execution time and never logged or shown to the model.
- Take-over and stop controls immediately pause automation.
- Browser crash is detected and surfaced; the task fails honestly.

**Primary risks:** prompt injection from page content, account actions, anti-bot defenses, session leakage.

---

## Stage 9 — Voice Interaction ✅ (shipped as Stage 3)

**Goal:** Natural hands-free use with local, private speech processing.

**Implementation status**

Shipped in `echo/voice` with a companion voice console in the frontend. All audio processing is local; there are no cloud speech calls.

**Delivered scope**

- Audio device enumeration and selection, live input level meter, and diagnostics (installed packages, model availability, latency, last error).
- Energy-gated VAD and endpointing (`echo/voice/vad.py`). Silero VAD was not needed for this stage and remains a possible upgrade.
- Wake word: default `echo` plus configurable aliases, detected by local Whisper keyword spotting on short energy-gated segments with a sensitivity threshold. openWakeWord remains the planned upgrade for lower CPU and fewer false wakes.
- STT: local `faster-whisper` (`tiny.en`, int8 CPU by default), configurable model/device/language, partial transcription while speaking.
- TTS: Windows SAPI via `pyttsx3`, voice selection, rate, volume, sentence-chunked queue. Piper remains the planned higher-quality offline engine.
- Three modes: push-to-talk, wake word, and continuous conversation with timeout; state machine `idle → listening → processing → speaking → idle` plus `muted` and `error`.
- Barge-in: sustained microphone energy during playback cancels TTS; a pre-roll ring buffer preserves the start of the interrupting utterance.
- Voice console UI: state orb with level-reactive ring, transcript with partial text, mute/stop-speaking/dismiss, mode selector, wake notice, and privacy indicator.
- Privacy: mic state always visible; mute suspends capture; raw audio memory-only by default; debug WAVs require explicit opt-in with count-based retention and a purge action.
- Latency instrumentation surfaced in `voice_timing` events and the diagnostics panel.

**Explicitly out of scope (unchanged):** always-on cloud STT, voice cloning, far-field multi-microphone arrays.

**Acceptance criteria**

- Wake word triggers on synthesized speech and non-wake phrases do not, both covered by tests.
- A spoken command is transcribed, answered through the shared chat turn service, and spoken back.
- Stop-speaking cancels playback within ~300 ms; barge-in cancels on sustained speech.
- Push-to-talk works with the wake word disabled.
- Audio is not written to disk by default; the claim is verified by test.
- Missing microphone or model files produce actionable errors, not crashes.

**Known limitations:** SAPI voice quality is system-dependent; `tiny.en` accuracy is modest; the first run downloads the Whisper model; wake-word reliability depends on microphone gain and sensitivity tuning.

**Primary risks:** false wakes, accent/STT accuracy, CPU contention, echo feedback.


---

## Stage 10 — Monitoring & Notifications ✅ (monitoring shipped as Stage 4)

**Goal:** ECHO notices what matters and tells the user without becoming noisy.

> **Shipped in build Stage 4:** the monitoring half of this stage is implemented in `echo/monitoring` and the System Observatory UI. Telemetry, Event Log watching, threshold persistence, deduplication, cooldowns, escalation, recovery, acknowledgement/resolution, profiles, persistence, REST/WS, and the live dashboard are complete and verified. Telegram delivery shipped as build Stage 5 through the remote relay's queued notifications. Windows toast, SMTP email, quiet hours, digest batching, and rule templates remain planned under Stage 11 (Notifications).

**Scope**

- Metrics sampler: CPU, memory, disk, battery, uptime, top processes (psutil).
- Windows Event Log watcher (selected channels), process start/stop watcher, file watchers.
- Declarative rule engine: condition, severity, cooldown, dedupe key, quiet hours, escalation.
- Notification channels: Windows toast, Telegram (allowlisted chat), SMTP email.
- Notification center UI with history, mute, and rule management.
- Health dashboard: daemon, providers, workers, DB, disk, last backup.
- Digest mode and rate limiting; storm suppression.
- Rule templates: low disk, high memory, service stopped, folder changed, failed logon burst.

**Explicitly out of scope:** remote camera/microphone surveillance, keylogging, employee monitoring.

**Acceptance criteria**

- A test rule fires once, respects cooldown, and deduplicates repeated events.
- Quiet hours suppress non-critical notifications and queue a digest.
- Telegram delivery is verified by API response ID; failures are retried with backoff and surfaced.
- Toast notifications work on Windows 11 and degrade gracefully on unsupported builds.
- Monitoring continues when the UI is closed.
- No notification includes secrets or full file contents.

**Primary risks:** alert fatigue, Event Log volume, notification permission issues, privacy perception.

---

## Stage 11 — Scheduler & Autonomy

**Goal:** Work that happens on time, within pre-authorized boundaries.

**Scope**

- Cron, interval, and one-shot schedules with timezone awareness and DST handling.
- Persistent job store; missed-run policy (skip, run once, catch up), coalescing, max instances.
- Task templates that bind a prompt, tool scopes, model, and autonomy level.
- Autonomy levels: Manual, Supervised (default), Trusted (bounded T1/T2 with grants).
- Unattended approval queue: pause and notify when approval is required; expire stale requests.
- Trigger sources: schedule, file event, system event, manual.
- Run history, next-run preview, enable/disable, and kill switch.
- Scheduler UI: calendar/list, run details, failure reasons, dry run.

**Explicitly out of scope:** distributed workers, cloud execution.

**Acceptance criteria**

- A job runs at the scheduled time and records a verifiable result.
- Restarting the daemon does not duplicate or silently drop runs; policy is explicit.
- A job requiring approval pauses and notifies instead of bypassing the gate.
- Revoking a grant prevents subsequent scheduled runs from using it.
- Overlapping runs are prevented per job.
- DST transitions produce the documented behavior in tests.

**Primary risks:** duplicate side effects, stale grants, unattended failure, timezone bugs.

---

## Stage 12 — Remote Contact & Optional Calls ✅ (remote relay shipped as Stage 5)

**Goal:** Reach the user when it matters, and allow safe remote decisions.

> **Shipped in build Stage 5:** the Telegram relay is implemented in `echo/remote` with the Remote Relay UI. Outbound long polling, bot token and owner verification, explicit one-time pairing, a read-only allowed-user list, `/ask`, `/task`, `/status`, `/health`, `/events`, `/tasks`, `/screenshot`, `/open`, `/approve`, `/deny`, `/pause`, and `/resume`, remote task history, owner-only screenshots, argument-bound approvals, rate limiting, credential blocking, command and rejection audit rows, severity-routed notifications with a persistence/backoff/collapse queue, and reconnect summaries are complete and verified. Email digests, phone-call escalation, the escalation matrix, quiet hours, and the incident timeline remain planned.

> **Verified in build Stage 5:** unauthorized IDs are rejected and audited; pairing codes are hashed, single-use, and expire; allowed users are read-only; `/approve` and desktop approval execute once; screenshots reach only the paired owner; rate limits are enforced and audited; credential requests are refused; queued notifications expire, collapse, and summarize on reconnect.

**Scope**

- Telegram bot with long polling (no inbound ports), allowlisted chat ID, and rate limits.
- Commands: `/status`, `/tasks`, `/approve <id>`, `/deny <id>`, `/stop`, `/ask <text>`.
- Short-lived, single-use approval tokens bound to argument hashes; expiry and audit.
- Escalation policy: toast → Telegram → email → optional phone call.
- Email digests via SMTP with app passwords in Credential Manager.
- Optional Twilio calls for critical events: scripted message, DTMF acknowledgment, spend cap, quiet hours, explicit enablement.
- Remote channel UI: connection status, test message, allowlist, escalation matrix.
- Incident timeline linking monitor event → notification → approval → action.

**Explicitly out of scope:** SMS gateways without user-owned accounts, inbound webhooks exposed to the internet.

**Acceptance criteria**

- An allowlisted chat can query status and approve/deny a pending action.
- Approvals expire and cannot be replayed; wrong chat IDs are ignored and audited.
- Phone calls are disabled by default and cannot run without an explicit spend cap.
- Escalation stops when the user acknowledges.
- Remote stop cancels running tasks and scheduled autonomy.
- No secrets or full file contents are sent over remote channels.

**Primary risks:** account takeover, approval phishing, paid-service misuse, notification privacy.

---

## Stage 13 — Hardening, Packaging & Release

**Goal:** A dependable Windows desktop product, not a dev server in a trench coat.

**Scope**

- Electron packaging with a hardened production configuration and signed installer (if certificates are available).
- Backend packaging (PyInstaller or embedded Python), version pinning, and reproducible builds.
- Single-instance coordination, daemon autostart, tray controls, and clean uninstall.
- Crash recovery, log rotation, database backup/restore, and migration rollback plan.
- Performance pass: startup, memory, UI responsiveness, DB indexes, worker isolation.
- Security review: Electron checklist, dependency audit, secret scan, prompt-injection regression suite.
- Accessibility pass: keyboard navigation, focus order, contrast, reduced motion, screen reader labels.
- Documentation: install, first-run, permissions, privacy, troubleshooting, backup, architecture updates.
- Release checklist and versioning policy.

**Explicitly out of scope:** auto-update until signing and rollback are proven.

**Acceptance criteria**

- Clean Windows 11 VM install → first run → local model → verified task → uninstall.
- Daemon crash is detected and recovered without data loss; UI shows the event.
- Installer and app pass the documented security checklist.
- Startup < 3 s for the UI shell on a typical machine; idle memory is documented.
- Backup/restore reproduces memory, settings, schedules, and audit history.
- No high/critical dependency vulnerabilities without a documented exception.
- All docs match shipped behavior.

**Primary risks:** antivirus false positives, Python bundling size, signing cost, installer complexity.

---

## Cross-cutting tracks

| Track | Applied in every stage |
|---|---|
| Security | Threat model update, input validation, least privilege, secret hygiene, injection fixtures. |
| Testing | Unit + integration + contract tests; Windows-specific tests run on a Windows runner. |
| Observability | Structured logs, correlation IDs, health checks, audit events, latency metrics. |
| Documentation | README status, architecture deltas, setup steps, known limitations. |
| UX | Loading, empty, error, offline, approval, and cancelled states designed — not afterthoughts. |
| Performance | Budgets tracked from M1; regressions treated as defects. |

---

## Release gates

- **Alpha (after M5):** safe conversation + agent loop + audited low-risk tools. No desktop/browser mutation.
- **Private beta (after M9):** files, desktop, browser, voice, monitoring. Supervised autonomy only.
- **v1.0 (after M13):** scheduler, remote approvals, packaged installer, security review complete.

---

## Deferred / explicitly not planned

- Mobile apps.
- Multi-user or team accounts.
- Cloud sync of memory or audit logs.
- Remote camera, microphone, or keylogging surveillance.
- Arbitrary code execution or shell access by the model.
- CAPTCHA solving or anti-bot evasion.
- A plugin marketplace; local, reviewed extensions only, if ever.
