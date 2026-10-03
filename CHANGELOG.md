# Changelog

All notable changes to mailbus are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [1.0.0] — 2026-10-03

First stable release: the bus survived a week of real production-line
adversity (two multi-day silent outages root-caused and fixed in-tree) and
delivered a complete three-tier game through a 10-agent pipeline with humans
only adjudicating.

### Reach & self-healing (M1)

- Outbound notify channels (desktop toast/notify-send, webhook
  Telegram/DingTalk(signed)/WeCom/generic, SMTP, file digest) with level
  routing and per-channel failure isolation; `mailbus notify test` for
  reach acceptance.
- Host sentinel (`tools/mailbus_sentinel.py`) watching from outside the
  mailbus process: new warns page immediately (outage drill: detected in
  7.6 min, target ≤10), persistent warns re-remind daily, recovery
  notifies, daily digest; Windows scheduled-task installer, Linux
  systemd-timer instructions.
- `mailbus acceptance status`: six health checks over the store (serve API,
  scheduler heartbeat, patrol/daily report continuity, token ledger,
  human-queue backlog) with machine-readable `--json`.
- Alerts wired: critical/warn alerts, scheduler job fail-streaks (default 3),
  abnormal adjudication entries (station vacancy / push budget / task
  timeout) all page the owner.

### Production-line reliability (M2)

- First-dispatch idempotency: a spawned work order is marked pushed in the
  agent inbox, so scan never pushes the same order twice; spawn failure
  leaves it pending with scan as the fallback pusher (at-least-once intact).
- Receipt tolerance: flat-path contract deliveries
  (`msg-results/msg-<task>-<step>.json`) and `status: done` receipts are
  digested (previously silently starved an 11-day task).
- Timeout escalation: exhausted reminders now escalate into the human
  adjudication queue and page the owner instead of dying as a bare status.
- Blocked-state recovery: chains resumed after adjudication gates
  (owner confirmation) continue expanding their planned stations;
  reminder loop exempts blocked tasks.
- `production-line` task template codifying the game-delivery line
  (planner → developer → reviewer → developer → integration → QA →
  reviewer → docs); station vacancy blocks at zero token.

### Outage fixes (root-caused from the 2026-09 incidents)

- In-container scan no longer dies on a claude push: the Windows PowerShell
  bridge is host-only and skipped inside containers; per-agent push
  exceptions are isolated so one poison message cannot starve the queue
  (3,680 consecutive scan failures were the symptom).
- Manager desk accept actions sent an invalid body (missing `decision`)
  and always failed silently — fixed, live-verified through four final
  acceptances.
- daily_report cron default moved out of the overnight host-sleep window.

### First-run experience (M3)

- Clean-clone drill: `pip install -e .` → `mailbus init` → `mailbus demo`
  completes a full work-order loop in ~7 s with zero dependencies.
- `mailbus doctor` available in the main CLI (self-diagnosis right after
  install, same engine as `mailbus-ops doctor`).

## [0.2.0] — 2026-09-20

Architecture upgrade waves 0–5 (18 slices), all CI-gated:

- Station-based dispatch (registry, vacancy adjudication, pin priority),
  task-flow template library, push budget circuit breaker + DLQ + forward
  hop limits, token ledger with per-task drill-down, message lifecycle
  trace replay, unified human adjudication queue, three-stage connection
  test, assembly cards, five-step onboarding collapsed to one, zero-dep
  demo + first-run wizard + README quick start.

## [0.1.0] — 2026-09-12

Initial public shape: file-based agent-to-agent message bus, adapters for
Hermes / OpenClaw / Codex / OpenCode / Claude Code, CLI, HTTP API, cockpit
dashboard.
