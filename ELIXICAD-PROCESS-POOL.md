# Persistent FreeCAD Process

## Overview

Currently, every model generation call in ElixiCad cold-spawns a fresh FreeCAD process via `Port.open/2` in `Elixihub.FreeCAD.Executor`. FreeCAD startup — Python interpreter init, OCCT library loading, workbench registration — costs 3–8 seconds per model, even when the actual CAD computation takes milliseconds.

This document describes replacing cold-spawn with a **persistent worker pool**: FreeCAD processes that start once, load all libraries, then accept scripts over stdin in a request/response loop. The per-model overhead drops from ~5s to ~50ms.

---

## Architecture

```
ElixiCad (Elixir)                        FreeCAD (Python)
─────────────────────────────────────────────────────────────────

Elixihub.FreeCAD.WorkerPool  ──────────▶  freecad --daemon
  (NimblePool / GenServer)                  └─ cadclaude_worker.py
        │                                        │
        │  stdin:  LENGTH\nSCRIPT               │  exec(script)
        │  stdout: READY / RESULT / ERROR        │
        │◀────────────────────────────────────── │
        │
Elixihub.FreeCAD.Executor  (unchanged public API)
```

The Elixir side manages a pool of warm worker processes. The FreeCAD fork ships a Python module (`cadclaude_worker.py`) that is the daemon entry point. The existing `Executor` public API — `execute/3`, `execute_raw/3` — remains unchanged; callers do not need to know about the pool.

---

## Part 1: FreeCAD Fork Changes

### 1.1 New file: `Mod/CadClaude/cadclaude_worker.py`

This module is the daemon script. It is invoked once at process startup and runs a read–execute–respond loop forever. It must be placed in a FreeCAD `Mod/` directory so it is importable from the binary root without needing `sys.path` surgery.

```python
"""
cadclaude_worker.py — Persistent FreeCAD worker for ElixiCad.

Protocol (over stdin/stdout, all messages newline-terminated):
  Startup:     worker emits  "READY\n"
  Per request:
    Elixir → worker:  "<length>\n<script bytes>"
    worker → Elixir:  "RESULT_START\n<stdout lines>\nRESULT_END\n"
                   or "ERROR_START\n<traceback>\nERROR_END\n"
  Shutdown:    Elixir → worker: "EXIT\n"
               worker exits cleanly
"""

import sys
import os
import traceback
import io


def _read_exactly(n):
    """Read exactly n bytes from stdin, blocking until available."""
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            raise EOFError("stdin closed while reading script body")
        buf += chunk
    return buf


def _run_script(script_source):
    """Execute script_source, capturing stdout/stderr. Returns (output, error)."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured = io.StringIO()
    sys.stdout = captured
    sys.stderr = captured

    try:
        exec(compile(script_source, "<cadclaude>", "exec"), {})
        error = None
    except SystemExit:
        # Scripts call sys.exit(0) — treat as clean completion
        error = None
    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return captured.getvalue(), error


def main():
    # Signal readiness to the Elixir pool manager
    sys.stdout.write("READY\n")
    sys.stdout.flush()

    while True:
        header = sys.stdin.readline()
        if not header:
            break  # stdin closed — parent died

        header = header.strip()

        if header == "EXIT":
            break

        try:
            length = int(header)
        except ValueError:
            sys.stdout.write("ERROR_START\n")
            sys.stdout.write(f"Bad header: {header!r}\n")
            sys.stdout.write("ERROR_END\n")
            sys.stdout.flush()
            continue

        try:
            script_bytes = _read_exactly(length)
            script = script_bytes.decode("utf-8")
        except Exception as e:
            sys.stdout.write("ERROR_START\n")
            sys.stdout.write(f"Failed to read script: {e}\n")
            sys.stdout.write("ERROR_END\n")
            sys.stdout.flush()
            continue

        output, error = _run_script(script)

        if error:
            sys.stdout.write("ERROR_START\n")
            sys.stdout.write(output)
            sys.stdout.write(error)
            sys.stdout.write("ERROR_END\n")
        else:
            sys.stdout.write("RESULT_START\n")
            sys.stdout.write(output)
            sys.stdout.write("RESULT_END\n")

        sys.stdout.flush()


if __name__ == "__main__":
    main()
```

### 1.2 CMake: register the new Mod

In `CMakeLists.txt` (or the `Mod/CadClaude/CMakeLists.txt` if CadClaude already has one), ensure the file is installed:

```cmake
# Mod/CadClaude/CMakeLists.txt
install(FILES cadclaude_worker.py
        DESTINATION ${CMAKE_INSTALL_PREFIX}/Mod/CadClaude)
```

### 1.3 Entry-point launcher script (macOS / Linux)

Add a thin shell wrapper `bin/freecad-worker` so ElixiCad can launch the daemon without knowing FreeCAD's internal Python path:

```bash
#!/usr/bin/env bash
# bin/freecad-worker
# Launch FreeCAD in persistent worker mode for ElixiCad.
# Usage: freecad-worker
set -euo pipefail

FREECAD_BIN="${FREECAD_PATH:-freecadcmd}"

exec "$FREECAD_BIN" -c "
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[0]), '..', 'Mod', 'CadClaude'))
import cadclaude_worker
cadclaude_worker.main()
"
```

On macOS with a `.app` bundle:

```bash
#!/usr/bin/env bash
FREECAD_BIN="/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"
MOD_DIR="/Applications/FreeCAD.app/Contents/Resources/Mod/CadClaude"

exec "$FREECAD_BIN" -c "
import sys
sys.path.insert(0, '$MOD_DIR')
import cadclaude_worker
cadclaude_worker.main()
"
```

### 1.4 Recommended build flags

When building the fork, strip unused workbenches to minimise startup time for the initial pool boot:

```cmake
cmake .. \
  -DBUILD_GUI=OFF \
  -DBUILD_FEM=OFF \
  -DBUILD_ROBOT=OFF \
  -DBUILD_ARCH=OFF \
  -DBUILD_SHIP=OFF \
  -DBUILD_PATH=OFF \
  -DBUILD_TECHDRAW=OFF \
  -DBUILD_SURFACE=OFF \
  -DBUILD_POINTS=OFF \
  -DBUILD_INSPECTION=OFF \
  -DBUILD_REVERSEENGINEERING=OFF \
  -DBUILD_OPENSCAD=OFF \
  -DBUILD_SPREADSHEET=OFF
```

---

## Part 2: ElixiCad Changes

### 2.1 New file: `elixicad/lib/elixihub/freecad/worker.ex`

A GenServer that owns a single FreeCAD OS process. Checked out from the pool for one job, then returned.

```elixir
defmodule Elixihub.FreeCAD.Worker do
  @moduledoc """
  Owns a single persistent FreeCAD OS process.
  Checked out from WorkerPool, used for one script execution, then returned.
  """
  use GenServer
  require Logger

  @ready_timeout 15_000   # ms to wait for initial READY signal
  @exec_timeout  240_000  # ms per script execution

  # ── Public API ──────────────────────────────────────────────────────────────

  def start_link(opts \\ []) do
    GenServer.start_link(__MODULE__, opts)
  end

  @doc "Execute script_source in this worker. Returns {:ok, output} | {:error, reason}."
  def execute(pid, script_source) do
    GenServer.call(pid, {:execute, script_source}, @exec_timeout + 5_000)
  end

  @doc "Terminate the underlying FreeCAD OS process."
  def stop(pid) do
    GenServer.stop(pid, :normal)
  end

  # ── GenServer callbacks ──────────────────────────────────────────────────────

  @impl true
  def init(_opts) do
    case start_freecad_process() do
      {:ok, port, os_pid} ->
        case await_ready(port) do
          :ok ->
            Logger.info("FreeCAD worker ready (OS PID #{os_pid})")
            {:ok, %{port: port, os_pid: os_pid}}

          {:error, reason} ->
            Port.close(port)
            {:stop, {:freecad_startup_failed, reason}}
        end

      {:error, reason} ->
        {:stop, reason}
    end
  end

  @impl true
  def handle_call({:execute, script_source}, _from, %{port: port} = state) do
    result = send_script(port, script_source)
    {:reply, result, state}
  end

  @impl true
  def terminate(_reason, %{port: port, os_pid: os_pid}) do
    # Send EXIT before killing so FreeCAD can close its document cleanly
    try do
      Port.command(port, "EXIT\n")
      :timer.sleep(200)
    rescue
      _ -> :ok
    end

    try do
      Port.close(port)
      System.cmd("kill", ["-9", to_string(os_pid)], stderr_to_stdout: true)
    rescue
      _ -> :ok
    end

    :ok
  end

  # ── Internals ────────────────────────────────────────────────────────────────

  defp start_freecad_process do
    bin = freecad_worker_binary()

    unless bin do
      {:error, "freecad-worker not found. Set FREECAD_WORKER_PATH or ensure it is on PATH."}
    else
      port =
        Port.open(
          {:spawn_executable, bin},
          [
            :binary,
            :exit_status,
            :stderr_to_stdout,
            env: [
              {~c"DISPLAY", ~c""},
              {~c"QT_QPA_PLATFORM", ~c"offscreen"}
            ]
          ]
        )

      os_pid =
        case Port.info(port, :os_pid) do
          {:os_pid, pid} -> pid
          _ -> nil
        end

      {:ok, port, os_pid}
    end
  end

  defp freecad_worker_binary do
    System.get_env("FREECAD_WORKER_PATH") ||
      System.find_executable("freecad-worker") ||
      check_macos_worker()
  end

  defp check_macos_worker do
    path = "/Applications/FreeCAD.app/Contents/MacOS/freecad-worker"
    if File.exists?(path), do: path
  end

  defp await_ready(port) do
    receive do
      {^port, {:data, data}} ->
        if String.contains?(data, "READY") do
          :ok
        else
          await_ready(port)
        end

      {^port, {:exit_status, code}} ->
        {:error, "FreeCAD exited during startup with code #{code}"}
    after
      @ready_timeout ->
        {:error, "Timed out waiting for FreeCAD READY signal"}
    end
  end

  defp send_script(port, script_source) do
    encoded = :unicode.characters_to_binary(script_source, :utf8)
    length = byte_size(encoded)
    Port.command(port, "#{length}\n#{encoded}")
    collect_response(port)
  end

  defp collect_response(port) do
    collect_response(port, "", @exec_timeout)
  end

  defp collect_response(port, acc, timeout) do
    deadline = System.monotonic_time(:millisecond) + timeout
    do_collect(port, acc, deadline)
  end

  defp do_collect(port, acc, deadline) do
    remaining = deadline - System.monotonic_time(:millisecond)

    if remaining <= 0 do
      {:error, :timeout}
    else
      receive do
        {^port, {:data, data}} ->
          buffer = acc <> data

          cond do
            String.contains?(buffer, "RESULT_END\n") ->
              output = extract_between(buffer, "RESULT_START\n", "\nRESULT_END")
              {:ok, output}

            String.contains?(buffer, "ERROR_END\n") ->
              reason = extract_between(buffer, "ERROR_START\n", "\nERROR_END")
              {:error, reason}

            true ->
              do_collect(port, buffer, deadline)
          end

        {^port, {:exit_status, code}} ->
          {:error, "FreeCAD worker exited unexpectedly (code #{code}). Output so far:\n#{acc}"}
      after
        min(remaining, 1_000) ->
          do_collect(port, acc, deadline)
      end
    end
  end

  defp extract_between(str, start_marker, end_marker) do
    case :binary.split(str, start_marker) do
      [_, rest] ->
        case :binary.split(rest, end_marker) do
          [content | _] -> String.trim(content)
          _ -> String.trim(rest)
        end

      _ ->
        String.trim(str)
    end
  end
end
```

### 2.2 New file: `elixicad/lib/elixihub/freecad/worker_pool.ex`

A pool supervisor built on `NimblePool`. Each pool member is a `Worker` GenServer.

```elixir
defmodule Elixihub.FreeCAD.WorkerPool do
  @moduledoc """
  Pool of persistent FreeCAD worker processes.
  Uses NimblePool for checkout/checkin lifecycle management.
  """
  @behaviour NimblePool

  require Logger

  @pool_size Application.compile_env(:elixihub, [:freecad_pool, :size], 2)
  @checkout_timeout 30_000

  # ── Pool API ─────────────────────────────────────────────────────────────────

  def start_link(opts \\ []) do
    NimblePool.start_link(
      worker: {__MODULE__, opts},
      pool_size: Keyword.get(opts, :pool_size, @pool_size),
      name: __MODULE__
    )
  end

  @doc "Execute a script using a pooled FreeCAD worker."
  def execute(script_source) do
    NimblePool.checkout!(
      __MODULE__,
      :checkout,
      fn _from, worker_pid ->
        result = Elixihub.FreeCAD.Worker.execute(worker_pid, script_source)
        {result, worker_pid}
      end,
      @checkout_timeout
    )
  end

  # ── NimblePool callbacks ──────────────────────────────────────────────────────

  @impl NimblePool
  def init_worker(pool_state) do
    {:ok, pid} = Elixihub.FreeCAD.Worker.start_link()
    {:ok, pid, pool_state}
  end

  @impl NimblePool
  def handle_checkout(:checkout, _from, worker_pid, pool_state) do
    {:ok, worker_pid, worker_pid, pool_state}
  end

  @impl NimblePool
  def handle_checkin(worker_pid, _from, worker_pid, pool_state) do
    # Worker is stateless between scripts — return it immediately
    {:ok, worker_pid, pool_state}
  end

  @impl NimblePool
  def terminate_worker(reason, worker_pid, pool_state) do
    Logger.info("Terminating FreeCAD worker (reason: #{inspect(reason)})")
    Elixihub.FreeCAD.Worker.stop(worker_pid)
    {:ok, pool_state}
  end
end
```

### 2.3 Update `Elixihub.Application`

Add the pool to the supervision tree in [elixicad/lib/elixihub/application.ex](elixicad/lib/elixihub/application.ex):

```elixir
children = [
  ElixihubWeb.Telemetry,
  Elixihub.Repo,
  {Ecto.Migrator, ...},
  {DNSCluster, ...},
  {Phoenix.PubSub, name: Elixihub.PubSub},
  {Registry, keys: :unique, name: Elixihub.AgentRegistry},
  {DynamicSupervisor, name: Elixihub.AgentSupervisor, strategy: :one_for_one},
  # ── NEW ──
  {Elixihub.FreeCAD.WorkerPool, pool_size: pool_size()},
  # ─────────
  ElixihubWeb.Endpoint
]
```

Add the helper at the bottom of `application.ex`:

```elixir
defp pool_size do
  Application.get_env(:elixihub, :freecad_pool)[:size] || 2
end
```

### 2.4 Update `Elixihub.FreeCAD.Executor`

Replace the `run_freecad/3` call in `execute/3` and `execute_raw/3` to route through the pool. The `wrap_with_exports/2`, `auto_fix/1`, and all helper functions are unchanged.

```elixir
# In execute/3 — replace File.write! + run_freecad call with:
def execute(script, output_dir, opts \\ []) do
  File.mkdir_p!(output_dir)
  script_path = Path.join(output_dir, "model.py")
  full_script = wrap_with_exports(script, output_dir)
  File.write!(script_path, full_script)

  run_via_pool(full_script, script_path, output_dir, opts)
end

defp run_via_pool(script_source, script_path, output_dir, opts) do
  lifecycle = Keyword.get(opts, :lifecycle)
  started_at = System.monotonic_time(:millisecond)

  maybe_lifecycle_event(lifecycle, %{
    event_type: "freecad.exec.started",
    actor_type: "freecad",
    message: "Starting FreeCAD execution (pooled)",
    data: %{script_path: Path.basename(script_path), output_dir: output_dir}
  })

  case Elixihub.FreeCAD.WorkerPool.execute(script_source) do
    {:ok, output} ->
      stl = find_file(output_dir, "*.stl")
      step = find_file(output_dir, "*.step")
      fcstd = find_file(output_dir, "*.FCStd")
      duration_ms = System.monotonic_time(:millisecond) - started_at

      if stl && File.exists?(stl) do
        maybe_lifecycle_event(lifecycle, %{
          event_type: "freecad.exec.completed",
          actor_type: "freecad",
          message: "FreeCAD execution completed (pooled)",
          metrics: %{duration_ms: duration_ms}
        })

        {:ok, %{
          output: output,
          script_path: script_path,
          fcstd_path: fcstd,
          step_path: step,
          stl_path: stl
        }}
      else
        maybe_lifecycle_event(lifecycle, %{
          event_type: "freecad.exec.failed",
          actor_type: "freecad",
          severity: "error",
          message: "FreeCAD execution failed — no STL produced",
          metrics: %{duration_ms: duration_ms},
          error_code: "stl_not_produced",
          error_message: String.slice(output, 0, 1000)
        })

        {:error, %{output: output, exit_code: 1}}
      end

    {:error, reason} ->
      duration_ms = System.monotonic_time(:millisecond) - started_at

      maybe_lifecycle_event(lifecycle, %{
        event_type: "freecad.exec.failed",
        actor_type: "freecad",
        severity: "error",
        message: "FreeCAD worker error",
        metrics: %{duration_ms: duration_ms},
        error_code: "worker_error",
        error_message: inspect(reason)
      })

      {:error, %{output: inspect(reason), exit_code: 1}}
  end
end
```

### 2.5 Add `nimble_pool` dependency

In [elixicad/mix.exs](elixicad/mix.exs), add to `deps/0`:

```elixir
{:nimble_pool, "~> 1.1"}
```

Then run:

```bash
cd elixicad && mix deps.get
```

### 2.6 Configuration

In [elixicad/config/config.exs](elixicad/config/config.exs):

```elixir
config :elixihub, :freecad_pool,
  size: 2

# Override in dev.exs / prod.exs as needed
```

In `config/dev.exs`:
```elixir
config :elixihub, :freecad_pool,
  size: 1  # Save memory in dev; one warm worker is plenty
```

---

## Part 3: Script Isolation Concern

The persistent worker re-uses the same Python process across scripts. Two issues require attention:

### 3.1 FreeCAD document accumulation

Each script opens (or reuses) `FreeCAD.ActiveDocument`. After the export footer calls `FreeCAD.closeDocument(doc.Name)`, the document is gone. However, if a script crashes before `closeDocument`, documents accumulate in memory.

**Fix:** In `cadclaude_worker.py`, add a cleanup step after each script run:

```python
# In _run_script(), after exec():
import FreeCAD
for name in list(FreeCAD.listDocuments().keys()):
    try:
        FreeCAD.closeDocument(name)
    except Exception:
        pass
```

### 3.2 Global namespace pollution

Scripts that set module-level globals (e.g. `LENGTH = 100`) persist in `{}` only because we pass a fresh `{}` dict to `exec()` each call. This is already handled by the `exec(compile(...), {})` pattern in `cadclaude_worker.py`.

---

## Part 4: Development Environment

### 4.1 Running manually (verifying the worker)

```bash
# From your FreeCAD fork build directory or .app:
FREECAD_PATH=/path/to/freecad ./bin/freecad-worker

# You should see:
# READY

# Then type (or pipe):
# 42
# import FreeCAD; print("hello from FreeCAD", FreeCAD.Version())

# Expected response:
# RESULT_START
# hello from FreeCAD ['1', '2', '0', ...]
# RESULT_END
```

### 4.2 Environment variables for dev

```bash
# .env or shell rc:

# Path to the freecad-worker launcher script
export FREECAD_WORKER_PATH=/path/to/freecad-fork/build/bin/freecad-worker

# Optional: disable pool, fall back to cold-spawn (for debugging)
export FREECAD_POOL_DISABLED=true
```

Add a fallback in `WorkerPool.execute/1` that checks `FREECAD_POOL_DISABLED` and delegates to the original `Executor.run_freecad/3` if set.

### 4.3 Starting ElixiCad with the pool

```bash
cd elixicad
FREECAD_WORKER_PATH=/path/to/freecad-worker mix phx.server
```

On startup you will see log lines like:

```
[info] FreeCAD worker ready (OS PID 12345)
[info] FreeCAD worker ready (OS PID 12346)
```

confirming both pool workers are warm before any requests arrive.

### 4.4 Verifying pool behaviour

Run a model creation request through the UI or API. The lifecycle events will now show `"Starting FreeCAD execution (pooled)"` and the `duration_ms` in `freecad.exec.completed` should be well under 1000ms for simple models (vs 5000–10000ms previously).

---

## File Change Summary

### FreeCAD fork

| File | Change |
|---|---|
| `Mod/CadClaude/cadclaude_worker.py` | New — daemon worker loop |
| `Mod/CadClaude/CMakeLists.txt` | Install `cadclaude_worker.py` |
| `bin/freecad-worker` | New — launcher script |

### ElixiCad

| File | Change |
|---|---|
| `elixicad/lib/elixihub/freecad/worker.ex` | New — single-process GenServer |
| `elixicad/lib/elixihub/freecad/worker_pool.ex` | New — NimblePool wrapper |
| `elixicad/lib/elixihub/application.ex` | Add `WorkerPool` to supervision tree |
| `elixicad/lib/elixihub/freecad/executor.ex` | Route through pool in `run_via_pool/4` |
| `elixicad/mix.exs` | Add `nimble_pool` dep |
| `elixicad/config/config.exs` | Pool size config |
