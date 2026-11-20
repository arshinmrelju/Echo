# ECHO — UI & Design System Specification

> **Document Status:** Stage 0 Complete  
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

5. **Audit & Log Inspector:**
   * Live streaming audit feed with correlation filter.
   * SHA-256 hash verification indicator verifying that the local audit trail has not been altered.

