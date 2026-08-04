# Build Identity in ElixiHub Settings — Design

**Date:** 2026-08-04
**Status:** Approved
**Repos touched:** FreeCAD fork (`/Users/user/dev/FreeCAD`), ElixiCAD (`/Users/user/dev/ElixiCAD`, elixihub app)

## Purpose

When diagnosing issues, we need to confirm exactly which FreeCAD fork build an ElixiCAD instance is running. The 2026-08 upstream sync showed why: the OCCT kernel (8.0.0-rc4) and embedded Python (3.11 → 3.13.5) both changed invisibly. ElixiHub's settings page should display the running engine's identity.

## Decision summary

- **Content:** FreeCAD version + git hash + branch, OCCT version, Python version. (elixifree version explicitly excluded — out of scope.)
- **Mechanism:** enrich the worker's `READY` boot line with a JSON payload. Chosen over an on-demand query script (pool-slot cost, latency) and a static build-info file (reports what's installed, not what's running; misleading after install swaps/rollbacks).
- **Source of truth:** the running worker process itself — cannot go stale or disagree with reality.

## Protocol change

Current: worker emits `READY\n` at boot.
New: worker emits one line:

```
READY {"freecad":"26.3.0","git":"f7605d21","branch":"sync/upstream-2026-08","occt":"8.0.0.rc4-e72d772e70","python":"3.13.5"}\n
```

Keys (all strings): `freecad`, `git` (short hash), `branch`, `occt`, `python`.

**Backward/forward compatibility:** ElixiHub's `await_ready` matches with `String.contains?(buffer, "READY")`, so an old hub accepts the new line, and a new hub accepts a bare `READY` from an old worker (build info is then `nil`/"unavailable"). No version negotiation needed.

## Component 1 — worker (`src/Mod/CadClaude/cadclaude_worker.py`, FreeCAD fork)

At boot, before emitting READY, collect (verified available live in the current build):

| Field | Source | Example |
|---|---|---|
| `freecad` | `FreeCAD.ConfigGet("BuildVersionMajor"/"Minor"/"Point")` joined | `26.3.0` |
| `git` | `FreeCAD.ConfigGet("BuildRevisionHash")[:10]` | `f7605d21c9` |
| `branch` | `FreeCAD.ConfigGet("BuildRevisionBranch")` | `sync/upstream-2026-08` |
| `occt` | `import Part; Part.OCC_VERSION` | `8.0.0.rc4-e72d772e70` |
| `python` | `sys.version.split()[0]` | `3.13.5` |

- The `import Part` at boot is deliberate: it also pre-warms the module every real workload imports, improving first-request latency.
- **Failure policy:** the entire collection is wrapped in one `try/except Exception`; on any failure emit bare `READY\n`. Version info must never break or delay boot beyond the Part import.
- JSON is emitted via `json.dumps` (stdlib), single line, no embedded newlines.

## Component 2 — ElixiHub worker GenServer (`lib/elixihub/freecad/worker.ex`)

- `await_ready/2` keeps the contains-"READY" accumulation logic (including the chunk-fragmentation handling) but now returns `{:ok, build_info | nil}`:
  - After matching, take the buffer content from `"READY"` to the next `\n` (accumulate further chunks if the newline hasn't arrived yet — the JSON payload can fragment across Port deliveries exactly like READY itself).
  - Trim, `Jason.decode` the remainder; on empty remainder or decode error → `nil` (never a crash).
- Store `build_info` in the GenServer state; expose `Worker.build_info(pid)` (a `GenServer.call`).

## Component 3 — pool API (`lib/elixihub/freecad/worker_pool.ex`)

`WorkerPool.build_info/0`: return the build info from any live worker (all workers run the same binary). Returns `nil` when no worker is up or the worker reported none.

## Component 4 — settings UI (`lib/elixihub_web/live/settings_live/show.ex`)

Read-only "FreeCAD Engine" section, fetched once on mount via `WorkerPool.build_info()`:

- FreeCAD `26.3.0 @ f7605d21c9 (sync/upstream-2026-08)`
- OCCT `8.0.0.rc4-e72d772e70`
- Python `3.13.5`
- When `nil`: show "Build info unavailable (no worker running or pre-versioning worker)".

Follow the existing section/markup conventions in `show.ex`.

## Testing

1. **Python (FreeCAD fork):** unit tests for the READY-line builder — output is `READY ` + valid JSON with exactly the 5 keys; a forced collection failure yields bare `READY`.
2. **Elixir parser tests:** `await_ready` with (a) bare `READY\n`, (b) `READY {json}\n` in one chunk, (c) payload split across chunk deliveries mid-JSON, (d) malformed JSON → `nil`, no crash.
3. **End-to-end (Elixir, tagged like other freecad-runtime tests):** boot a real worker, assert `WorkerPool.build_info/0` returns a map with the 5 keys.

## Out of scope

- elixifree package version reporting
- Per-worker version display (pool is homogeneous)
- Version-mismatch alerting/warnings
