# ECHO — Personal AI Assistant

> A local-first, Windows-native AI agent that can see, hear, remember, act — and ask before it does something that matters.

**Status:** Stage 2 — ECHO Desktop Control Functional & Verified.
ECHO now possesses native Windows desktop interaction through a strictly typed, permissioned tool system. No arbitrary command lines or unvetted scripts are ever executed by the AI.

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
*(All 27 backend tests across core, memory, brain, and desktop tools pass.)*

### 2. Launch Development Environment
```powershell
.\scripts\dev.ps1
```
Open **`http://127.0.0.1:5173`** and click **Desktop Control** in the left sidebar to access the Control Panel.

---

## Roadmap Summary

| Stage | Theme | Status |
|---|---|---|
| 0 | Architecture, security model, UI direction, roadmap | ✅ Complete |
| 1 | Foundation: ECHO Core (Daemon, SQLite WAL, UI Shell, Memory, Brain) | ✅ Complete |
| 2 | Desktop Control: Tool Registry, Win32 API, Screen, Mouse, Keyboard, Approvals | ✅ Complete |
| 3 | Persistent Memory: Vector Embeddings & Reciprocal Rank Fusion | Planned |
| 4 | Tools, Permissions (T0–T4) & Hash-Chained Audit Trails | Planned |
| 5 | Agent Planner & Verification Runtime State Machine | Planned |
| 6 | File Intelligence & Safe Operations | Planned |
| 7 | Advanced Desktop Control (OCR & Accessibility Trees) | Planned |
| 8 | Browser Automation (Playwright Sandboxing) | Planned |
| 9 | Voice Interaction (openWakeWord, Whisper, Piper) | Planned |
| 10 | Monitoring & Notifications (Event Log, Hardware Telemetry) | Planned |
| 11 | Scheduler & Autonomous Routines | Planned |
| 12 | Remote Contact & Escalation Calls | Planned |
| 13 | Desktop Packaging, Hardening & Release | Planned |
