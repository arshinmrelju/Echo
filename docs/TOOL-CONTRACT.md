# ECHO — Tool Contract Specification

> **Document Status:** Stage 0 Complete  
> **Last Updated:** November 2026  
> **Module Target:** `echo/tools`

---

## 1. Tool Declaration Contract

Every tool in ECHO must inherit from the `BaseTool` class and provide a complete static schema using Pydantic models. Raw dictionaries or unvalidated argument maps are strictly prohibited.

```python
from abc import ABC, abstractmethod
from typing import Type, Generic, TypeVar
from pydantic import BaseModel, Field
from enum import Enum

class RiskTier(str, Enum):
    T0_READ = "T0"
    T1_WORKSPACE_MUTATION = "T1"
    T2_SENSITIVE_EXTERNAL = "T2"
    T3_HIGH_IMPACT = "T3"
    T4_CRITICAL = "T4"

class ToolScope(str, Enum):
    SYSTEM = "system"
    FILES = "files"
    DESKTOP = "desktop"
    BROWSER = "browser"
    NETWORK = "network"
    NOTIFICATIONS = "notifications"

TArgs = TypeVar("TArgs", bound=BaseModel)
TResult = TypeVar("TResult", bound=BaseModel)

class ToolVerification(BaseModel):
    verified: bool
    evidence: str
    diff: str | None = None

class ToolExecutionResult(BaseModel):
    success: bool
    output: str
    data: dict | None = None
    verification: ToolVerification
    execution_time_ms: float

class BaseTool(ABC, Generic[TArgs, TResult]):
    name: str
    description: str
    version: str = "1.0.0"
    risk_tier: RiskTier
    scope: ToolScope
    args_schema: Type[TArgs]
    requires_approval: bool = False
    timeout_seconds: float = 30.0

    @abstractmethod
    async def preflight_check(self, args: TArgs) -> tuple[bool, str | None]:
        """Perform preliminary validation (e.g. check if target path exists and is allowed)."""
        pass

    @abstractmethod
    async def execute(self, args: TArgs) -> TResult:
        """Execute the tool's core functionality."""
        pass

    @abstractmethod
    async def verify(self, args: TArgs, result: TResult) -> ToolVerification:
        """Inspect the real environment to verify that the side-effect took place."""
        pass
```

---

## 2. The 7-Step Tool Execution Pipeline

```
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. Schema Validation (Pydantic model parse & type check)    │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Valid typed args
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 2. Authorization & Scope Check (Token, risk tier, grants)   │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Authorized
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 3. Preflight Check (Check paths, system state, lockfiles)   │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Preflight passed
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 4. Approval Gate (If T2+, verify session grant or prompt UI)│
  └──────────────────────────────┬──────────────────────────────┘
                                 │ User approved / Grant active
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 5. Execution within Timeout Sandbox                         │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Raw result
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 6. Verification Gate (Inspect OS/filesystem/DOM for proof)  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Verified evidence
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 7. Audit & Event Dispatch (Append to hash-chained log)      │
  └─────────────────────────────────────────────────────────────┘
```

---

## 3. Verification Principles

A core tenet of ECHO is: **"Never pretend an action succeeded without verifying it."**

* **Filesystem Write:** After writing a file, the tool must stat the filesystem, calculate the SHA-256 hash of the written file, and verify that bytes written match expectations.
* **Desktop Click:** After clicking an element or typing text, the tool must query the UI Automation tree to verify that focus shifted or window state updated.
* **Browser Navigation:** After instructing Playwright to navigate, the tool must wait for `domcontentloaded` or network idle and verify the final URL and page title.
* **Service / Process Action:** After starting or stopping a process, the tool must inspect the OS process table to verify its running or terminated state.

If verification fails, the tool execution is flagged as **failed or unverified**, preventing the AI planner from assuming the environment state changed.

---

## 4. Initial Core Tools Inventory (Stage 4 Target)

1. `system.get_time`: Query current system time, timezone, and uptime (T0).
2. `system.get_metrics`: Query CPU usage, RAM utilization, and disk free space (T0).
3. `files.read_text`: Read text from allowlisted directories up to 2MB (T0).
4. `files.list_dir`: List directory contents with size, timestamps, and types (T0).
5. `files.write_scratch`: Write temporary scratch file in `%LOCALAPPDATA%\Echo\scratch` (T1).
6. `files.copy_file`: Copy file between permitted roots with hash check (T2).
7. `files.recycle_file`: Send a file to Windows Recycle Bin (T3).
8. `desktop.get_active_window`: Read title and process of the foreground window (T0).
9. `desktop.capture_screenshot`: Capture full screen or region as visual evidence (T1).
10. `browser.navigate`: Open Playwright browser to an allowlisted domain (T2).

