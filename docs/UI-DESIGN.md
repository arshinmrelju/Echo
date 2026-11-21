# ECHO — UI & Design System Specification

> **Document Status:** Stage 5 Remote Relay UI Implemented  
> **Last Updated:** November 2026  
> **Visual Identity:** Professional Autonomous AI Command Center

---

## 1. Visual Identity & Design Philosophy

ECHO is an operational command center for your Windows workstation. It is **not** a whimsical, toy chat interface or a generic SaaS dashboard. The design language combines **industrial precision, tactile responsiveness, and futuristic minimalism**.

### Aesthetic Pillars:
1. **Obsidian Dark Theme:** Deep, velvety blacks and dark greys (`#080B10`, `#0D1117`, `#161B22`) that reduce eye fatigue during long sessions.
2. **Neon Cyan & Electric Blue Accents:** Cyan (`#00F0FF`) signifies live agent attention, tool execution, and verified states; Electric Blue (`#0070F3`) represents knowledge, memory, and calm idle states.
3. **Restrained Glassmorphism:** Micro-diffuse translucent panels (`backdrop-blur-md`, subtle border glows) that give layered depth without impairing performance or readability.
4. **Information Density & Typography:** Monospace metrics (`JetBrains Mono` or `Consolas`) paired with crisp sans-serif headings (`Inter` or `Segoe UI Variable`).
5. **Living System Indicators:** Fluid pulsating orbs, audio spectrum visualizers, and task timeline nodes that reflect true real-time backend state.

---

## 2. Color Tokens & Palette

```css
:root {
  /* Surface Layers */
  --bg-deep-void: #05070A;       /* Background foundation */
  --bg-surface: #0B0E14;         /* Main application card surface */
  --bg-surface-elevated: #121721;/* Floating modals, tooltips, dialogs */
  --bg-glass: rgba(11, 14, 20, 0.75);

  /* Borders */
  --border-subtle: #1C2331;
  --border-active: #00F0FF;
  --border-glass: rgba(255, 255, 255, 0.08);

  /* Primary Accent: Neon Cyan */
  --cyan-primary: #00F0FF;
  --cyan-glow: rgba(0, 240, 255, 0.25);
  --cyan-dim: #008B99;

  /* Secondary Accent: Electric Cobalt */
  --blue-primary: #0070F3;
  --blue-glow: rgba(0, 112, 243, 0.25);

  /* Status Colors */
  --status-success: #00E676;     /* Green - Verified */
  --status-warning: #FFB300;     /* Amber - Awaiting Approval */
  --status-danger: #FF1744;      /* Red - Error / Emergency Stop */
  --status-purple: #7928CA;      /* Purple - Autonomous Routine */

  /* Text Typography */
  --text-primary: #F0F6FC;
  --text-secondary: #8B949E;
  --text-muted: #484F58;
}
```

---

## 3. Core Screen Architecture & Layout

The UI uses a **3-zone modular layout**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: Status Orb · Daemon Connection · Active Model · Emergency Stop│
├───────────┬────────────────────────────────────────────┬───────────────┤
│ LEFT RAIL │ MAIN STAGE                                 │ RIGHT DRAWER  │
│           │                                            │               │
│ [Command] │ ┌────────────────────────────────────────┐ │ [Live Telemetry│
│ [Tasks]   │ │ Conversation & Agent Reasoning Stream  │ │  CPU: 18%     │
│ [Memory]  │ │                                        │ │  RAM: 42%     │
│ [Files]   │ │ [Step 1: Inspect Folder]               │ │  Disk: 65%    │
│ [Browser] │ │  ↳ Verified hash matched               │ │               │
│ [Monitor] │ │ [Step 2: Awaiting User Approval]       │ │ Active Grants │
│ [Audit]   │ │  ↳ [ Approve ]  [ Deny ]               │ │  • files:read │
│ [Settings]│ └────────────────────────────────────────┘ │               │
│           │ ┌────────────────────────────────────────┐ │ Audio Visual  │
│           │ │ Universal Command & Voice Prompt Bar   │ │  ~/\~/\~~     │
│           │ └────────────────────────────────────────┘ │               │
└───────────┴────────────────────────────────────────────┴───────────────┘
```

### Key Screen Views:
1. **Command Center (Home):**
   * Central Hero Status Orb reflecting state (`IDLE`, `LISTENING`, `THINKING`, `EXECUTING`, `ALERT`).
   * Unified conversation flow displaying both user messages and expandable agent reasoning blocks.
   * Universal Command Bar with voice-activation toggle, file drag-and-drop target, and quick slash commands (`/goal`, `/plan`, `/schedule`).

2. **Task & Execution Visualizer:**
   * Interactive tree diagram of multi-step plans.
   * Per-step card showing thought, tool name, input arguments, execution timing, and verification badge.
   * One-click manual take-over or pause button.

3. **Memory Explorer:**
   * Searchable interactive view of semantic memories, working session context, and episodic summaries.
   * Edit, delete, and source attribution tags for every stored fact ("Why do you remember this?").

4. **Security & Approval Modal:**
   * High-urgency glass dialog presenting target file paths, proposed actions, and calculated risk tier.
   * Diff preview for file modifications.

5. **Voice Console:**
   * Instrument strip docked above the composer: state orb, level meter, transcript, mode selector, and microphone controls.
   * Always states whether the channel and microphone are open; hiding the console never closes the microphone.

6. **Audit & Log Inspector:**
   * Live streaming audit feed with correlation filter.
   * SHA-256 hash verification indicator verifying that the local audit trail has not been altered.

---

## 4. Voice Console Specification

The voice UI is an instrument panel, not a chat toy. It reuses the existing obsidian/cyan language and avoids generic gradient blobs, fake waveforms, or decorative particles. Every animated element maps to a real backend value.

### Layout
- Docked as a bordered strip above `MessageInput`; open/close lives on the microphone button in the composer and the sidebar footer chip.
- Header rail (`font-mono`, 10px, letterspaced): `VOICE / I-O` · `CHANNEL OPEN|CLOSED` · `MIC OPEN|MUTED|CLOSED` · `WAKE "ECHO"` when in wake mode.
- Main row: orb (80px) · center readout · control column (150px).
- Push-to-talk pad appears only in PUSH mode; speaker strip appears only while speaking.

### State Orb (`VoiceOrb.tsx`)
- 48 calibration ticks, every fourth tick major; outer rotor speed varies by state.
- Counter-rotating dashed arc; paused when idle or muted.
- Level-reactive ring: radius `48 + level × 9`, stroke width `1 + level × 2.4`.
- Processing draws a crosshair; mute draws a red slash; offline renders as muted.
- State palette:

| State | Color | Motion | Label |
|---|---|---|---|
| Idle | `#008B99` | slow rotor, 22s | `READY` |
| Listening | `#00F0FF` | 18s, live level | `LISTENING` |
| Processing | `#0070F3` | fast 7s, crosshair | `TRANSCRIBING` |
| Speaking | `#00F0FF` | 12s, live level | `SPEAKING` |
| Muted | `#8B949E` | static, red slash | `MUTED` |
| Error | `#FF1744` | 22s | `FAULT` |

Color is never the only signal: every state also prints a text label and the header rail states microphone status explicitly.

### Readout
- Mode selector `PUSH` / `WAKE` / `LIVE` (push-to-talk, wake word, continuous), with the active mode in cyan.
- 32-bar level meter; bars extinguish when muted.
- STT latency in milliseconds and completed turn count.
- Transcript panel: partial text italic with a blinking cyan caret; final text in primary text color; empty captures show an amber "No speech recognised" message; idle shows a mode-specific hint.
- Privacy line: shield icon plus either "Raw audio stays in memory · nothing written to disk" or the explicit debug-recording count. Errors render in danger red.

### Controls
- `Enable mic` (cyan), `Mute mic` / `Unmute mic` (amber when muted), `Stop` (disabled unless speaking), `Setup`, `Dismiss` (continuous mode only), `Off`.
- `HOLD TO TALK` pad: pointer capture plus Space/Enter keyboard support; while held it turns solid cyan with `RECORDING — RELEASE TO SEND`.
- Speaking strip offers an inline `interrupt` action.

### Voice Settings Modal (`VoiceSettingsModal.tsx`)
- `01 Input`: device, sample rate, VAD threshold, silence timeout, max utterance, partial transcription, STT model/language.
- `02 Output`: SAPI voice, rate, volume, test-speech action.
- `03 Privacy`: debug recordings toggle, retention count, purge action, explicit default copy that audio is memory-only.
- `04 Diagnostics`: installed package checks, model availability, device list, latency, last error.
- Save sends the full form; structural changes (device, model, mode) restart the voice session.

### Motion & Accessibility
- Rotor durations per state; all animation pauses under `prefers-reduced-motion`.
- Buttons carry `title` descriptions; the orb exposes an `aria-label` with the current state.
- Muted and offline states are communicated by text and the red slash, not color alone.

---

## 5. System Observatory Specification

The monitoring dashboard (`SystemDashboard.tsx`) is a full-screen instrument panel over the obsidian/cyan system. It is a readout, not a fictional dashboard: every number comes from `/api/v1/monitoring` or a `monitor_*` WebSocket event, and unavailable probes render explicit unavailability instead of placeholders.

### Layout
- Modal overlay (`max-w-1280`, `91vh`) with a header rail: `SYSTEM OBSERVATORY`, `LIVE|IDLE`, active profile, poll interval, last poll, uptime.
- Header actions: `STOP`/`START` engine toggle, refresh, close.
- Availability strip: Event Log (`CONNECTED|UNAVAILABLE`), thermal sensor (`source|NO SENSOR`), battery percentage, active alert count.
- Tabs: `OVERVIEW`, `ALERTS n`, `EVENT FEED`, `CONFIG`.

### Overview
- Six numbered metric tiles (`01 CPU` … `06 THERMAL`), each with a mono micro-label, large value, detail line, and a real sparkline fed by the history buffer.
- Storage tile turns amber/red based on the lowest free volume; network shows `ONLINE|OFFLINE`, latency, and live down/up rates.
- Thermal shows `NO SENSOR` with the backend reason when no hardware bridge is exposed.
- Secondary cards: volumes (per-drive free/used/percent), host state (uptime, boot time, processes, platform, swap), top memory processes, signal availability, and active alerts with inline `RESOLVE`.

### Alerts & Event Feed
- Status filters `ALL | ACTIVE | RECOVERED | RESOLVED`; severity chips use `info` grey, `notice` blue, `warning` amber, `critical` red.
- Alert rows show severity, category, title, message, occurrence count, first-seen relative time, acknowledgement state, and actions (`ACK`, `RESOLVE`).
- Event feed filters by category and severity; each row shows local time, severity, title, category, kind (`alert`, `acknowledged`, `recovered`, Windows event), and message.

### Config
- Profile cards (`QUIET`, `BALANCED`, `STRICT`) apply immediately and show `ACTIVE`.
- Feature switches for each monitored domain.
- Numeric fields for cadence, retention, cooldown, escalation, recovery margins, and every threshold; list fields for disk paths, probe targets, and monitored applications.
- `SAVE` sends the full draft; validation errors from the daemon are displayed inline. `RESET` reloads the last persisted settings.

### Visual Rules
- Severity is communicated by both color and text (`CRITICAL`, `WARNING`, …); the sidebar badge mirrors severity and shows a count.
- Only real telemetry is plotted. Sparklines derive from the backend history buffer, and probes without data render an em dash.
- Animations are limited to state cues (alert pulse, refresh spin, live dot) and respect `prefers-reduced-motion` where applicable.

---

## 6. Remote Relay Specification

The Remote Relay modal (`RemoteRelay.tsx`) is the control surface for the Telegram channel. It follows the Observatory language — obsidian surface, cyan live states, mono micro-labels — and shows only values returned by `/api/v1/remote/*` or `remote_*` WebSocket events.

### Layout
- Modal overlay (`max-w-1180`, `90vh`) over `#07090E`, with a header rail: `REMOTE RELAY`, state chip (`LINKED` / `OFFLINE` / `IDLE` / `PAUSED`), `@bot_username`, and `COMMANDS BLOCKED` while paused.
- Sub-line: `TRANSPORT`, `INBOUND 0`, last heartbeat, queue depth.
- Header actions: `STOP`/`START`, `PAUSE`/`RESUME`, reconnect, refresh, close.
- Availability strip: `OWNER`, `BOT TOKEN` (`CONFIGURED …hint` or `MISSING`), `SCREENSHOTS` (`OWNER ONLY` / `OFF`), `PENDING APPROVALS` count.
- Tabs: `LINK`, `ACCESS n`, `NOTIFICATIONS n`, `AUDIT`.

### LINK
- Credentials card: masked bot-token password input, numeric owner ID, save action.
- Relay stats: PC state, ECHO state, health summary, last poll, current task, poll attempts, uptime, last error.
- Pairing card: generate, copy, cancel; countdown to expiry; the code is displayed once and never re-shown from storage.
- Privacy posture list: 0 inbound ports, outbound long polling only, owner-only screenshots, credential requests blocked, dangerous actions approval-gated.
- Paused state replaces the action row with `RESUME` and shows the pause reason.

### ACCESS
- Allowed-user table: display name, Telegram ID, role (`READ-ONLY`), last seen, transport, remove action.
- Add-user form accepts a numeric ID; non-numeric input is rejected inline.
- Pending dangerous actions: tool name, requesting Telegram ID, argument summary, `/approve <id>` hint, and expiry.
- Owner card and a plain-language access-rule list (private chats only, 20 commands/min, fresh approval, no credentials).

### NOTIFICATIONS
- Routing toggles for critical alerts, warnings, task results, approval requests, connectivity, and monitoring events.
- Minimum event severity selector and event-category filter; remote screenshot toggle; `SAVE POLICY`.
- Queue state counters (`Queued`, `Sending`, `Sent`, `Failed`, `Expired`, `Suppressed`), TTL, batch size, flush interval, send rate, and max items.
- Notification table: local time, severity chip, message, status, attempts, and `RETRY` for failed rows; `SEND TEST` enqueues a probe.
- Offline behavior copy states that rows persist in SQLite, expire by severity, collapse on reconnect, and are replaced by a downtime summary.

### AUDIT
- Remote command log: time, actor (owner name or unknown Telegram ID), command, status (`OK`, `REJECTED`, `RATE LIMITED`, …), and detail.
- Remote task list: goal, status, origin (`/task` or text), Telegram ID, and relative time of the last update.

### Visual Rules
- State is never color-only: paused, offline, unauthorized, and rejected paths also print a label.
- Tokens are never rendered in full; the API returns a hint only.
- Draft edits are protected from the 5-second status poll — the form initializes once per open and only reloads after save or explicit refresh.
- The sidebar entry shows relay state and queued-notification count, so an offline relay or growing queue is visible without opening the modal.


