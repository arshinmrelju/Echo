# ECHO — Personal AI Assistant

> A local-first, Windows-native AI agent that can see, hear, remember, act — and ask before it does something that matters.

**Status:** Stage 0 — Architecture & Planning complete. Stage 1 (Foundation & Shell) is next.
There is no runnable application yet; this repository currently contains the architecture, security model, UI direction, and staged delivery plan.

---

## Why ECHO is not a chatbot

A chatbot answers. ECHO **operates**.

ECHO is designed as a persistent personal agent that runs on the user's Windows machine, understands intent, plans multi-step work, calls explicitly defined tools, verifies the result, remembers what matters, monitors the system, and reaches the user remotely when something needs attention.

It is built around one rule:

> **The model may propose actions. Only the runtime may perform them.**

---

## Product principles

| Principle | Meaning |
|---|---|
| Windows-first | Native integration with Windows UI Automation, toast notifications, Event Log, Credential Manager, and the filesystem. |
| Local-first | Data, memory, logs, and defaults stay on the machine. Cloud models and remote channels are explicit opt-ins. |
| Agent, not autocomplete | A bounded plan → act → observe → verify loop with real tool execution. |
| Permissioned autonomy | Capability scopes, risk tiers, time-bound grants, and per-action approval for sensitive work. |
| Verified, never theatrical | No tool result is reported as successful without evidence. No placeholder buttons. |
| Modular by construction | Independent services with typed interfaces; optional modules can fail without taking down the core. |
| Auditable by default | Every side effect, approval, and failure is recorded with correlation IDs. |
| Private by default | Secrets in Windows Credential Manager, redacted logs, no telemetry unless enabled. |
| Free/open-source first | Local models, local speech, local storage; paid services only where no credible free option exists. |

---

## Planned capabilities

- **Conversation and reasoning** with local (Ollama / OpenAI-compatible) or cloud models.
- **Persistent memory**: working context, episodic history, semantic facts, and preferences with hybrid retrieval.
- **Agent runtime**: multi-step planning, tool calls, observation, verification, cancellation, and resume.
- **Desktop control**: windows, apps, screenshots, OCR, keyboard and mouse — with approval gates.
- **File intelligence**: indexing, extraction, semantic + keyword search, and safe file operations.
- **Browser automation**: Playwright with domain allowlists, accessibility snapshots, and approval for consequential actions.
- **Voice**: offline wake word, VAD, speech-to-text, text-to-speech, barge-in, and push-to-talk fallback.
- **Monitoring**: system metrics, Event Log, file and process watchers, and declarative alert rules.
- **Notifications**: Windows toasts, Telegram, email, and optional automated phone calls for critical escalation.
- **Scheduling and autonomy**: cron/interval/one-shot jobs, missed-run policies, and supervised autonomous tasks.
- **Remote control**: status, approval, denial, and emergency stop from an allowlisted Telegram chat.
- **Premium command-center UI**: dark, cyan-accented, keyboard-first, real-time task timeline.

---

## Architecture at a glance

```text
┌───────────────────────────── Windows desktop ──────────────────────────────┐
│                                                                            │
│   Electron shell                                                           │
│   ┌──────────────────────────────────────────────┐                         │
│   │ React + TypeScript + Vite + Tailwind         │                         │
│   │ Command Center · Tasks · Memory · Audit      │                         │
│   └───────────────────────┬──────────────────────┘                         │
│                           │ REST + WebSocket (loopback, token auth)        │
│   ┌───────────────────────▼──────────────────────┐                         │
│   │ ECHO daemon — Python 3.12 / FastAPI          │                         │
│   │                                              │                         │
│   │ kernel: config · events · lifecycle · health │                         │
│   │ brain · agent · tools · memory · permissions │                         │
│   │ audit · scheduler · monitoring               │                         │
│   │ workers: voice · browser · file indexer      │                         │
│   └───────────┬───────────────────┬──────────────┘                         │
│               │                   │                                        │
│        SQLite (WAL)          artifacts / logs                              │
│        %LOCALAPPDATA%\Echo                                                 │
└───────────────┼────────────────────────────────────────────────────────────┘
                │ explicit, scoped, opt-in
     ┌──────────┴───────────┬──────────────────┬─────────────────┐
     ▼                      ▼                  ▼                 ▼
 Local LLM             Cloud LLM          Telegram / SMTP    Twilio (opt-in)
 (Ollama, etc.)        (if configured)    notifications      critical calls
```

The backend is a **daemon**, not a child of the UI. The UI can close; monitoring, schedules, and notifications continue. Electron attaches to a running daemon or starts one.

---

## Planned repository layout

```text
D:\Echo
├─ echo/                         Python application package
│  ├─ core/                      kernel, config, events, DB, paths, security
│  ├─ api/                       FastAPI app, routes, WebSocket gateway, schemas
│  ├─ brain/                     model providers, routing, prompts, streaming
│  ├─ agent/                     planner, executor, verifier, task state machine
│  ├─ tools/                     tool registry, contracts, built-in tools
│  ├─ memory/                    working/episodic/semantic memory, retrieval
│  ├─ desktop/                   Windows UI Automation, input, capture, OCR
│  ├─ files/                     indexing, extraction, search, safe file ops
│  ├─ browser/                   Playwright session and page intelligence
│  ├─ voice/                     wake word, VAD, STT, TTS, audio devices
│  ├─ monitoring/                system/file/process watchers, rules engine
│  ├─ notifications/             toast, Telegram, email, escalation
│  ├─ scheduler/                 jobs, triggers, missed-run policy
│  ├─ permissions/               scopes, risk tiers, grants, approvals
│  └─ audit/                     append-only audit log and verification
├─ frontend/                     React + TypeScript + Vite + Tailwind UI
├─ desktop/                      Electron main, preload, packaging config
├─ tests/                        unit, integration, contract, security tests
├─ docs/                         architecture, roadmap, threat model, contracts
├─ scripts/                      dev, test, lint, package scripts
├─ pyproject.toml
├─ .env.example
└─ README.md
```

---

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, modules, data model, APIs, agent runtime, failure behavior. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Stages 0–13 with deliverables, acceptance criteria, and dependencies. |
| [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md) | Assets, trust boundaries, threats, mitigations, and security invariants. |
| [docs/TOOL-CONTRACT.md](docs/TOOL-CONTRACT.md) | How tools are declared, validated, approved, executed, and verified. |
| [docs/UI-DESIGN.md](docs/UI-DESIGN.md) | Visual language, layout, components, motion, accessibility, and screens. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision records and the Electron packaging gate. |

---

## Non-negotiable security rules

1. The LLM never executes code, shell commands, or arbitrary tools directly.
2. Every tool call is schema-validated, permission-checked, and audited.
3. Destructive, external, or sensitive actions require approval bound to the exact arguments.
4. Tool output is untrusted data — never instructions, never a permission grant.
5. No success is reported without a tool-specific verification step.
6. Secrets live in Windows Credential Manager or environment variables, never in source, logs, or the database.
7. The daemon binds to loopback only and requires a per-run token.
8. A global emergency stop cancels agents, browser sessions, and scheduled work immediately.
9. Audit records are append-only and hash-chained.
10. Optional modules fail soft; core chat and system visibility keep working.

---

## Getting started

Not available yet. Stage 1 will introduce:

```powershell
# Planned
.\scripts\dev.ps1          # backend + frontend in development mode
.\scripts\test.ps1         # backend + frontend test suites
```

Prerequisites will be documented when the first executable stage lands: Windows 10 22H2+ / Windows 11, Python 3.12+, Node.js 22 LTS+, and optionally Ollama.

---

## Roadmap summary

| Stage | Theme | Status |
|---|---|---|
| 0 | Architecture, security model, UI direction, roadmap | ✅ Complete |
| 1 | Foundation: kernel, config, DB, events, API, UI shell | Next |
| 2 | AI brain and streaming conversation | Planned |
| 3 | Persistent memory | Planned |
| 4 | Tools, permissions, approvals, audit | Planned |
| 5 | Agent planner/executor | Planned |
| 6 | File intelligence | Planned |
| 7 | Desktop control | Planned |
| 8 | Browser automation | Planned |
| 9 | Voice interaction | Planned |
| 10 | Monitoring and notifications | Planned |
| 11 | Scheduler and autonomy | Planned |
| 12 | Remote contact and optional calls | Planned |
| 13 | Hardening, packaging, release | Planned |

See [docs/ROADMAP.md](docs/ROADMAP.md) for scope and acceptance criteria.

---

## Open decisions

These are intentionally unresolved until Stage 1, and do not block the architecture:

- Primary local model and available GPU/VRAM.
- Default wake phrase (working assumption: “Hey Echo”).
- Primary remote channel (working assumption: Telegram bot with an allowlisted chat ID).
- Default autonomy level for new installs (working assumption: **Supervised**).
- Whether phone-call escalation will be enabled at all (Twilio is paid and opt-in).
- Project license.

---

## License

TBD. The intent is a permissive open-source license; no license has been selected yet.
