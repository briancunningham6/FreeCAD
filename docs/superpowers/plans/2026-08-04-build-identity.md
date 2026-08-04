# Build Identity in ElixiHub Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The FreeCAD worker reports its build identity (FreeCAD version/git/branch, OCCT, Python) on its `READY` boot line, and ElixiHub displays it in a read-only "FreeCAD Engine" section of the settings page.

**Architecture:** The worker collects version info in-process at boot and appends a single-line JSON payload to `READY`. ElixiHub's `Worker` GenServer parses it during `await_ready`, stores it in state, and exposes it through `WorkerPool.build_info/0` → `Settings.freecad_build_info/0` → the `settings_content` layout component. Compatibility both directions is free: the hub matches on `String.contains?(buffer, "READY")` and treats an absent/bad payload as `nil`.

**Tech Stack:** Python 3 stdlib (`json`) in `cadclaude_worker.py`; Elixir (GenServer, NimblePool, Jason, Phoenix LiveView/HEEx) in elixihub.

**Spec:** `docs/superpowers/specs/2026-08-04-build-identity-design.md` (approved).

## Global Constraints

- Protocol line format exactly: `READY {"freecad":"26.3.0","git":"f7605d21c9","branch":"sync/upstream-2026-08","occt":"8.0.0.rc4-e72d772e70","python":"3.13.5"}\n` — keys `freecad`, `git` (10-char short hash), `branch`, `occt`, `python`, all strings, single line.
- Version collection must NEVER break or delay worker boot (single `try/except Exception` → bare `READY\n` fallback). Decode failures on the hub side must NEVER crash the GenServer (fall back to `nil`).
- Two repos: FreeCAD fork `/Users/user/dev/FreeCAD` (branch `feat/elixifree-core`) and elixihub `/Users/user/dev/ElixiCAD/elixihub` (repo root `/Users/user/dev/ElixiCAD`). Commit in the repo you changed; stage ONLY your files (the ElixiCAD repo has pre-existing dirt, e.g. `docs/ontology/individuals-generated.yaml` — never stage it).
- Elixir tests requiring a real FreeCAD runtime are tagged `@tag :freecad` (excluded by default in `test/test_helper.exs`).
- Do not modify the worker protocol beyond the READY line. `RESULT_START`/`ERROR_START` framing is untouched.

## File Structure

| File | Responsibility |
|---|---|
| `src/Mod/CadClaude/cadclaude_worker.py` (FreeCAD) | `_collect_build_info()` (dict or None), `_ready_line(info)` (str), wired into `main()` |
| `src/Mod/CadClaude/tests/test_worker_protocol.py` (FreeCAD, new) | Pure-Python tests for both functions (no FreeCAD required) |
| `lib/elixihub/freecad/worker.ex` (elixihub) | `parse_ready_buffer/1` (pure, testable), `await_ready` returns `{:ok, build_info \| nil}`, state gains `build_info`, `build_info/1` API |
| `lib/elixihub/freecad/worker_pool.ex` (elixihub) | `build_info/0` via NimblePool checkout, `nil` on any failure |
| `lib/elixihub/settings.ex` (elixihub) | `freecad_build_info/0` delegate (web layer stays off the pool module) |
| `lib/elixihub_web/components/layouts.ex` (elixihub) | `freecad_build_info` attr + "FreeCAD Engine" section in `settings_content` |
| `lib/elixihub_web/live/settings_live/show.ex` (elixihub) | mount assign + pass-through |
| `test/elixihub/freecad/worker_ready_test.exs` (elixihub, new) | parse tests + `:freecad`-tagged e2e |
| `test/elixihub_web/components/settings_content_test.exs` (elixihub, new) | component render test for both states |

---

### Task 1: Worker READY payload (FreeCAD repo)

**Files:**
- Modify: `src/Mod/CadClaude/cadclaude_worker.py` (top imports ~line 20; new functions before `main()`; `main()` line ~309)
- Test: `src/Mod/CadClaude/tests/test_worker_protocol.py` (create)

**Interfaces:**
- Produces: the READY protocol line consumed by Task 2 — `READY\n` or `READY <compact-json>\n` with string keys `freecad`, `git`, `branch`, `occt`, `python`.
- `_collect_build_info() -> dict | None`; `_ready_line(info: dict | None) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `src/Mod/CadClaude/tests/test_worker_protocol.py`:

```python
"""Tests for the READY-line build-identity payload (design spec 2026-08-04).

Runs under plain pytest — cadclaude_worker has no top-level FreeCAD import,
and _collect_build_info degrades to None when FreeCAD is unavailable.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cadclaude_worker as w


def test_ready_line_bare_when_no_info():
    assert w._ready_line(None) == "READY\n"


def test_ready_line_embeds_single_line_json():
    info = {
        "freecad": "26.3.0",
        "git": "f7605d21c9",
        "branch": "sync/upstream-2026-08",
        "occt": "8.0.0.rc4-e72d772e70",
        "python": "3.13.5",
    }
    line = w._ready_line(info)
    assert line.startswith("READY ")
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line[len("READY "):]) == info


def test_ready_line_falls_back_on_unserializable_info():
    assert w._ready_line({"bad": object()}) == "READY\n"


def test_collect_build_info_none_without_freecad():
    if "FreeCAD" in sys.modules:
        import pytest
        pytest.skip("running inside FreeCAD; collection would succeed")
    assert w._collect_build_info() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/dev/FreeCAD && python3 -m pytest src/Mod/CadClaude/tests/test_worker_protocol.py -v`
Expected: FAIL/ERROR with `AttributeError: module 'cadclaude_worker' has no attribute '_ready_line'` (import of the module itself must succeed).

- [ ] **Step 3: Implement**

In `src/Mod/CadClaude/cadclaude_worker.py`: add `import json` to the top-level imports (next to `import sys`, `import os`). Then add above `main()`:

```python
def _collect_build_info():
    """Build identity of this FreeCAD process, or None if unavailable.

    Imported lazily so the module stays importable outside FreeCAD.
    The Part import doubles as a pre-warm of the module every real
    workload uses. Never raises.
    """
    try:
        import FreeCAD
        import Part

        return {
            "freecad": ".".join(
                FreeCAD.ConfigGet(key)
                for key in ("BuildVersionMajor", "BuildVersionMinor", "BuildVersionPoint")
            ),
            "git": FreeCAD.ConfigGet("BuildRevisionHash")[:10],
            "branch": FreeCAD.ConfigGet("BuildRevisionBranch"),
            "occt": Part.OCC_VERSION,
            "python": sys.version.split()[0],
        }
    except Exception:  # noqa: BLE001 — version info must never break boot
        return None


def _ready_line(info):
    """The READY protocol line: bare, or with a single-line JSON payload."""
    if not info:
        return "READY\n"
    try:
        return "READY %s\n" % json.dumps(info, separators=(",", ":"), sort_keys=True)
    except Exception:  # noqa: BLE001
        return "READY\n"
```

In `main()`, replace:

```python
    # Signal readiness to the Elixir pool manager
    if not _write(protocol_out, "READY\n"):
        return
```

with:

```python
    # Signal readiness to the Elixir pool manager, with build identity
    # (design spec 2026-08-04); falls back to bare READY on any failure.
    if not _write(protocol_out, _ready_line(_collect_build_info())):
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/dev/FreeCAD && python3 -m pytest src/Mod/CadClaude/tests/test_worker_protocol.py -v`
Expected: 4 passed.

- [ ] **Step 5: Live protocol check against the running build**

The installed production copy is separate from the repo; test via the repo copy explicitly:

```bash
S=/private/tmp/claude-503/-Users-user-dev-FreeCAD/d57de4ca-3321-42c1-a9d7-6a6010c42cba/scratchpad
SCRIPT='print("ok")'
LEN=$(printf '%s' "$SCRIPT" | wc -c | tr -d ' ')
{ printf '%s\n' "$LEN"; printf '%s' "$SCRIPT"; sleep 4; printf 'EXIT\n'; } | \
  env -u FREECAD_PATH -u FREECAD_WORKER_PATH \
      FREECAD_WORKER_PY=/Users/user/dev/FreeCAD/src/Mod/CadClaude/cadclaude_worker.py \
      ~/freecad-cadclaude/bin/freecad-worker 2>/dev/null | head -1
```

Expected: one line starting `READY {"branch":"sync/upstream-2026-08",` containing `"freecad":"26.3.0"`, `"git":"f7605d21c9"`, `"occt":"8.0.0.rc4-e72d772e70"`, `"python":"3.13.5"`. (The git hash reflects the compiled binary — it stays `f7605d21c9` until the next C++ rebuild; Python-only changes don't move it. That is correct: it identifies the engine build.)

- [ ] **Step 6: Commit (FreeCAD repo)**

```bash
cd /Users/user/dev/FreeCAD
git add src/Mod/CadClaude/cadclaude_worker.py src/Mod/CadClaude/tests/test_worker_protocol.py
git commit -m "feat(cadclaude): report build identity on worker READY line"
```

---

### Task 2: Hub-side READY parsing + Worker.build_info (elixihub)

**Files:**
- Modify: `lib/elixihub/freecad/worker.ex` (`await_ready` ~line 138; `init` ~line 31; public API ~line 18)
- Test: `test/elixihub/freecad/worker_ready_test.exs` (create)

**Interfaces:**
- Consumes: the READY line format from Task 1.
- Produces: `Elixihub.FreeCAD.Worker.parse_ready_buffer(binary) :: {:ready, map | nil} | :incomplete`; `Elixihub.FreeCAD.Worker.build_info(pid) :: map | nil`. Worker state map gains `:build_info`.

- [ ] **Step 1: Write the failing parse tests**

Create `test/elixihub/freecad/worker_ready_test.exs`:

```elixir
defmodule Elixihub.FreeCAD.WorkerReadyTest do
  use ExUnit.Case, async: true

  alias Elixihub.FreeCAD.Worker

  @payload ~s({"freecad":"26.3.0","git":"f7605d21c9","branch":"sync/upstream-2026-08","occt":"8.0.0.rc4-e72d772e70","python":"3.13.5"})

  describe "parse_ready_buffer/1" do
    test "bare READY yields nil build info" do
      assert {:ready, nil} = Worker.parse_ready_buffer("READY\n")
    end

    test "READY with JSON payload yields decoded map" do
      assert {:ready, info} = Worker.parse_ready_buffer("READY " <> @payload <> "\n")
      assert info["freecad"] == "26.3.0"
      assert info["git"] == "f7605d21c9"
      assert info["occt"] == "8.0.0.rc4-e72d772e70"
      assert info["python"] == "3.13.5"
      assert info["branch"] == "sync/upstream-2026-08"
    end

    test "incomplete until the newline after READY arrives (payload fragmentation)" do
      assert :incomplete = Worker.parse_ready_buffer("REA")
      assert :incomplete = Worker.parse_ready_buffer("READY {\"freecad\":\"26")
      assert {:ready, %{"freecad" => "26.3.0"}} =
               Worker.parse_ready_buffer("READY {\"freecad\":\"26.3.0\"}\n")
    end

    test "noise before READY is tolerated" do
      assert {:ready, nil} = Worker.parse_ready_buffer("some stderr leak\nREADY\n")
    end

    test "malformed JSON degrades to nil, never raises" do
      assert {:ready, nil} = Worker.parse_ready_buffer("READY {not json}\n")
    end

    test "non-object JSON degrades to nil" do
      assert {:ready, nil} = Worker.parse_ready_buffer("READY [1,2]\n")
    end
  end
end
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub/freecad/worker_ready_test.exs`
Expected: FAIL — `Worker.parse_ready_buffer/1 is undefined`.

- [ ] **Step 3: Implement in worker.ex**

Add to the Public API section (after `stop/1`):

```elixir
  @doc "Build identity reported by the worker at boot (map), or nil if unknown."
  def build_info(pid) do
    GenServer.call(pid, :build_info)
  end

  @doc false
  # Pure parser for the boot buffer. Public for tests.
  # {:ready, build_info | nil} once "READY...\n" is fully buffered; :incomplete otherwise.
  def parse_ready_buffer(buffer) do
    case String.split(buffer, "READY", parts: 2) do
      [_pre, rest] ->
        case String.split(rest, "\n", parts: 2) do
          [payload, _after] -> {:ready, decode_build_info(payload)}
          [_no_newline_yet] -> :incomplete
        end

      [_no_ready] ->
        :incomplete
    end
  end

  defp decode_build_info(payload) do
    case String.trim(payload) do
      "" ->
        nil

      json ->
        case Jason.decode(json) do
          {:ok, %{} = info} -> info
          _ -> nil
        end
    end
  end
```

Rework `await_ready` (keeping the chunk-accumulation comment, now extended to the payload):

```elixir
  # Accumulates chunks until a full "READY[ payload]\n" line is buffered.
  # Fixes a fragmentation bug in the naive per-chunk approach: both the
  # 6-byte "READY\n" and its optional JSON payload can arrive split across
  # multiple Port deliveries, so we parse the accumulated buffer each time.
  defp await_ready(port, acc \\ "") do
    receive do
      {^port, {:data, data}} ->
        buffer = acc <> data

        case parse_ready_buffer(buffer) do
          {:ready, build_info} -> {:ok, build_info}
          :incomplete -> await_ready(port, buffer)
        end

      {^port, {:exit_status, code}} ->
        {:error, "FreeCAD exited during startup with code #{code}"}
    after
      @ready_timeout ->
        {:error, "Timed out waiting for FreeCAD READY signal"}
    end
  end
```

Update `init/1`'s success branch to match the new return and store the info:

```elixir
        case await_ready(port) do
          {:ok, build_info} ->
            Logger.info("FreeCAD worker ready (OS PID #{os_pid})")
            {:ok, %{port: port, os_pid: os_pid, build_info: build_info}}
```

(The `{:error, reason}` branch is unchanged.) Add the callback next to the existing `handle_call`:

```elixir
  @impl true
  def handle_call(:build_info, _from, state) do
    {:reply, state.build_info, state}
  end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub/freecad/worker_ready_test.exs`
Expected: 6 passed. Also run `mix test test/elixihub/freecad/` to confirm no regression in the other freecad tests (the `:freecad`-tagged ones stay excluded).

- [ ] **Step 5: Commit (ElixiCAD repo)**

```bash
cd /Users/user/dev/ElixiCAD
git add elixihub/lib/elixihub/freecad/worker.ex elixihub/test/elixihub/freecad/worker_ready_test.exs
git commit -m "feat(elixihub): parse build identity from FreeCAD worker READY line"
```

---

### Task 3: Pool + Settings accessors, live e2e (elixihub)

**Files:**
- Modify: `lib/elixihub/freecad/worker_pool.ex` (public API, after `execute/1` ~line 48)
- Modify: `lib/elixihub/settings.ex` (next to `claude_code_health/0` ~line 95)
- Test: `test/elixihub/freecad/worker_ready_test.exs` (append)

**Interfaces:**
- Consumes: `Worker.build_info(pid)` from Task 2.
- Produces: `Elixihub.FreeCAD.WorkerPool.build_info() :: map | nil`; `Elixihub.Settings.freecad_build_info() :: map | nil` (consumed by Task 4).

- [ ] **Step 1: Write the failing tests (append to worker_ready_test.exs)**

```elixir
  describe "Settings.freecad_build_info/0" do
    test "returns nil when the pool is not running" do
      # The test env does not start the FreeCAD pool; this exercises the
      # graceful-degradation path the settings page relies on.
      assert Elixihub.Settings.freecad_build_info() == nil
    end
  end

  describe "end to end against a real worker" do
    @tag :freecad
    test "a booted worker reports the five build-identity keys" do
      {:ok, pid} = Elixihub.FreeCAD.Worker.start_link([])
      info = Elixihub.FreeCAD.Worker.build_info(pid)
      assert %{} = info

      for key <- ["freecad", "git", "branch", "occt", "python"] do
        assert is_binary(info[key]), "missing/invalid #{key}: #{inspect(info)}"
      end

      Elixihub.FreeCAD.Worker.stop(pid)
    end
  end
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub/freecad/worker_ready_test.exs`
Expected: the Settings test fails with `function Elixihub.Settings.freecad_build_info/0 is undefined`; the `:freecad` test is excluded (skipped) by default.

- [ ] **Step 3: Implement**

In `lib/elixihub/freecad/worker_pool.ex`, after `execute/1`:

```elixir
  @doc """
  Build identity of the running FreeCAD engine (map with "freecad", "git",
  "branch", "occt", "python"), or nil if no worker/pool is available or the
  worker predates identity reporting. All workers run the same binary, so
  any pooled worker's answer is authoritative.
  """
  def build_info do
    NimblePool.checkout!(
      __MODULE__,
      :checkout,
      fn _from, worker_pid ->
        {Elixihub.FreeCAD.Worker.build_info(worker_pid), worker_pid}
      end,
      5_000
    )
  catch
    :exit, _reason -> nil
  end
```

In `lib/elixihub/settings.ex`, next to `claude_code_health/0`:

```elixir
  @doc "Build identity of the FreeCAD engine for diagnostics display, or nil."
  def freecad_build_info do
    Elixihub.FreeCAD.WorkerPool.build_info()
  end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub/freecad/worker_ready_test.exs`
Expected: all pass, 1 excluded (`:freecad`).

- [ ] **Step 5: Run the `:freecad`-tagged e2e against the real engine**

Requires the repo-side worker from Task 1 (env vars point the worker script at the repo copy):

```bash
cd /Users/user/dev/ElixiCAD/elixihub
FREECAD_WORKER_PATH=$HOME/freecad-cadclaude/bin/freecad-worker \
FREECAD_WORKER_PY=/Users/user/dev/FreeCAD/src/Mod/CadClaude/cadclaude_worker.py \
  mix test test/elixihub/freecad/worker_ready_test.exs --include freecad
```

Expected: e2e test passes with all five keys. If the Worker's spawn env drops these vars, check `ElixifreeSource.worker_env()` and the `freecad_worker_binary()` resolution in worker.ex — `FREECAD_WORKER_PATH` is already honored there.

- [ ] **Step 6: Commit (ElixiCAD repo)**

```bash
cd /Users/user/dev/ElixiCAD
git add elixihub/lib/elixihub/freecad/worker_pool.ex elixihub/lib/elixihub/settings.ex elixihub/test/elixihub/freecad/worker_ready_test.exs
git commit -m "feat(elixihub): expose FreeCAD build identity via pool and settings"
```

---

### Task 4: Settings UI section (elixihub)

**Files:**
- Modify: `lib/elixihub_web/components/layouts.ex` (attrs ~line 492; markup after the Claude-health div ~line 673)
- Modify: `lib/elixihub_web/live/settings_live/show.ex` (mount ~line 8; settings_content call ~line 37)
- Test: `test/elixihub_web/components/settings_content_test.exs` (create)

**Interfaces:**
- Consumes: `Settings.freecad_build_info/0` from Task 3.
- Produces: `settings_content` attr `freecad_build_info` (`:any`, default `nil`) — map with string keys or nil.

- [ ] **Step 1: Write the failing component tests**

Create `test/elixihub_web/components/settings_content_test.exs`:

```elixir
defmodule ElixihubWeb.SettingsContentBuildInfoTest do
  use ExUnit.Case, async: true

  import Phoenix.LiveViewTest

  defp render_settings(build_info) do
    render_component(&ElixihubWeb.Layouts.settings_content/1,
      defaults: %{},
      view_mode_options: [],
      legend_mode_options: [],
      freecad_build_info: build_info
    )
  end

  test "shows build identity when available" do
    html =
      render_settings(%{
        "freecad" => "26.3.0",
        "git" => "f7605d21c9",
        "branch" => "sync/upstream-2026-08",
        "occt" => "8.0.0.rc4-e72d772e70",
        "python" => "3.13.5"
      })

    assert html =~ "FreeCAD Engine"
    assert html =~ "26.3.0 @ f7605d21c9 (sync/upstream-2026-08)"
    assert html =~ "8.0.0.rc4-e72d772e70"
    assert html =~ "3.13.5"
  end

  test "shows unavailable state when nil" do
    html = render_settings(nil)
    assert html =~ "FreeCAD Engine"
    assert html =~ "Build info unavailable"
  end
end
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub_web/components/settings_content_test.exs`
Expected: FAIL — no "FreeCAD Engine" in rendered output (unknown attrs are ignored by function components; if the test errors on required attrs instead, keep the three required ones shown above).

- [ ] **Step 3: Implement**

In `lib/elixihub_web/components/layouts.ex`, add with the other `settings_content` attrs (next to `attr :claude_code_health, ...`):

```elixir
  attr :freecad_build_info, :any, default: nil
```

Add this block in `settings_content` immediately AFTER the Claude-health `<div :if={match?({:unavailable, _error}, @claude_code_health)}>...</div>` block (inside the same grid):

```heex
            <div class="md:col-span-2 rounded-lg border border-zinc-700 bg-zinc-900/60 p-4 text-sm">
              <p class="font-semibold text-zinc-200">FreeCAD Engine</p>
              <dl :if={@freecad_build_info} class="mt-2 grid gap-1 text-xs text-zinc-400">
                <div class="flex gap-2">
                  <dt class="w-20 shrink-0 text-zinc-500">FreeCAD</dt>
                  <dd>
                    {@freecad_build_info["freecad"]} @ {@freecad_build_info["git"]} ({@freecad_build_info["branch"]})
                  </dd>
                </div>
                <div class="flex gap-2">
                  <dt class="w-20 shrink-0 text-zinc-500">OCCT</dt>
                  <dd>{@freecad_build_info["occt"]}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="w-20 shrink-0 text-zinc-500">Python</dt>
                  <dd>{@freecad_build_info["python"]}</dd>
                </div>
              </dl>
              <p :if={!@freecad_build_info} class="mt-2 text-xs text-zinc-500">
                Build info unavailable (no worker running or pre-versioning worker).
              </p>
            </div>
```

In `lib/elixihub_web/live/settings_live/show.ex`: append to the mount assign pipeline:

```elixir
     |> assign(:freecad_build_info, Settings.freecad_build_info())
```

and add to the `<Layouts.settings_content ...>` call:

```heex
        freecad_build_info={@freecad_build_info}
```

(Other `settings_content` call sites — e.g. the one near layouts.ex:1007 — are untouched; the attr defaults to `nil` and renders the unavailable state.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test test/elixihub_web/components/settings_content_test.exs && mix compile --warnings-as-errors`
Expected: 2 passed; clean compile.

- [ ] **Step 5: Commit (ElixiCAD repo)**

```bash
cd /Users/user/dev/ElixiCAD
git add elixihub/lib/elixihub_web/components/layouts.ex elixihub/lib/elixihub_web/live/settings_live/show.ex elixihub/test/elixihub_web/components/settings_content_test.exs
git commit -m "feat(elixihub): show FreeCAD engine build identity in settings"
```

---

### Task 5: Deploy worker to production install + full verification

**Files:**
- None (deploy + verification only; the installed `~/freecad-cadclaude/Mod/CadClaude/cadclaude_worker.py` is a copy refreshed from the repo)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Refresh the installed worker copy**

```bash
cmake --install /Users/user/dev/FreeCAD/build-sync --prefix ~/freecad-cadclaude
grep -c '_collect_build_info' ~/freecad-cadclaude/Mod/CadClaude/cadclaude_worker.py
```

Expected: install succeeds; grep count ≥ 2 (definition + call), proving the installed copy carries the change.

- [ ] **Step 2: Clean-env production smoke**

```bash
env -u FREECAD_PATH -u FREECAD_WORKER_PATH -u FREECAD_WORKER_PY \
  /private/tmp/claude-503/-Users-user-dev-FreeCAD/d57de4ca-3321-42c1-a9d7-6a6010c42cba/scratchpad/worker-smoke-prod.sh
```

Expected: `WORKER SMOKE: PASS` (the smoke script greps `^READY`, which still matches the enriched line — if it used exact-match it would need updating; it uses `grep -q '^READY'`).

- [ ] **Step 3: Full elixihub freecad e2e against the production install (no env overrides)**

```bash
cd /Users/user/dev/ElixiCAD/elixihub
env -u FREECAD_PATH -u FREECAD_WORKER_PY \
  FREECAD_WORKER_PATH=$HOME/freecad-cadclaude/bin/freecad-worker \
  mix test test/elixihub/freecad/worker_ready_test.exs --include freecad
```

Expected: all pass including e2e, now via the installed copy.

- [ ] **Step 4: Full elixihub test suite regression check**

Run: `cd /Users/user/dev/ElixiCAD/elixihub && mix test`
Expected: no new failures vs. the pre-task state (run `git stash && mix test` first if a baseline is needed, then `git stash pop` — only if failures appear and their provenance is unclear).

---

## Self-Review

- **Spec coverage:** protocol line (Task 1), failure policy both sides (Tasks 1–2), `parse_ready_buffer` fragmentation cases incl. mid-payload split (Task 2 tests), pool + settings accessors (Task 3), UI section incl. unavailable state (Task 4), all three test layers from the spec (Tasks 1/2/4 + e2e in 3/5). ✅
- **Placeholders:** none — all code inline. ✅
- **Type consistency:** `build_info` is a string-keyed map end-to-end; `parse_ready_buffer` return shape used consistently; attr name `freecad_build_info` uniform across layouts/show/tests. ✅
