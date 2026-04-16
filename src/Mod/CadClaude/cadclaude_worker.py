"""
cadclaude_worker.py — Persistent FreeCAD worker for ElixiCad.

Protocol (over stdin/stdout, all messages newline-terminated):
  Startup:     worker emits  "READY\\n"
  Per request:
    Elixir → worker:  "<length>\\n<script bytes>"
    worker → Elixir:  "RESULT_START\\n<stdout lines>\\nRESULT_END\\n"
                   or "ERROR_START\\n<traceback>\\nERROR_END\\n"
  Shutdown:    Elixir → worker: "EXIT\\n"
               worker exits cleanly

FreeCAD/OCCT writes its own diagnostic messages to stdout (fd 1) via
C-level PrintMessage. To prevent these from corrupting the protocol
stream, we redirect fd 1 → fd 2 at the OS level before entering the
loop, then use fd 2 (a fresh duplicate of the original stdout) as the
protocol pipe.
"""

import sys
import os
import traceback
import io
import time
import resource
import json


def _redirect_freecad_noise():
    """
    Redirect C-level fd 1 to fd 2 so FreeCAD/OCCT PrintMessage output
    goes to stderr and cannot corrupt the protocol stream on stdout.
    Returns a new file object wrapping the original fd 1.
    """
    # Duplicate original stdout fd before redirecting
    original_stdout_fd = os.dup(1)
    # Point fd 1 at stderr so C-level writes go there
    os.dup2(2, 1)
    # Python stdout now needs to write to the original fd
    protocol_out = os.fdopen(original_stdout_fd, "w", buffering=1)
    return protocol_out


def _readline():
    """Read a line from stdin using the binary buffer to avoid read-ahead corruption.
    Python's text-layer sys.stdin.readline() pre-buffers bytes, which causes
    sys.stdin.buffer.read(n) to miss those bytes. Always use the binary layer.
    """
    return sys.stdin.buffer.readline().decode("utf-8")


def _read_exactly(n):
    """Read exactly n bytes from stdin using the binary buffer, blocking until available."""
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            raise EOFError("stdin closed while reading script body")
        buf += chunk
    return buf


def _run_script(script_source):
    """
    Execute script_source, capturing stdout/stderr.
    Returns (output, error) where error is None on success.
    Also closes any FreeCAD documents left open by the script (cleanup
    after crashes that skip FreeCAD.closeDocument).
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured = io.StringIO()
    sys.stdout = captured
    sys.stderr = captured

    t_start = time.monotonic()
    ru_before = resource.getrusage(resource.RUSAGE_SELF)

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

    t_end = time.monotonic()
    ru_after = resource.getrusage(resource.RUSAGE_SELF)

    wall_ms = round((t_end - t_start) * 1000)
    cpu_user_ms = round((ru_after.ru_utime - ru_before.ru_utime) * 1000)
    cpu_sys_ms = round((ru_after.ru_stime - ru_before.ru_stime) * 1000)
    # ru_maxrss is in bytes on macOS, kilobytes on Linux
    rss_bytes = ru_after.ru_maxrss
    if sys.platform == "darwin":
        process_rss_mb = round(rss_bytes / (1024 * 1024), 2)
    else:
        process_rss_mb = round(rss_bytes / 1024, 2)

    metrics = {
        "wall_ms": wall_ms,
        "cpu_user_ms": cpu_user_ms,
        "cpu_sys_ms": cpu_sys_ms,
        "process_rss_mb": process_rss_mb,
    }

    # Close any documents left open (e.g. after a crash mid-script)
    try:
        import FreeCAD
        for name in list(FreeCAD.listDocuments().keys()):
            try:
                FreeCAD.closeDocument(name)
            except Exception:
                pass
    except Exception:
        pass

    output = captured.getvalue()
    output += f"\nCADCLAUDE_METRICS: {json.dumps(metrics)}"
    return output, error


def _write(protocol_out, *lines):
    """Write lines to protocol_out, returning False if the pipe is broken."""
    try:
        for line in lines:
            protocol_out.write(line)
        protocol_out.flush()
        return True
    except (BrokenPipeError, OSError):
        return False


def main():
    protocol_out = _redirect_freecad_noise()

    # Signal readiness to the Elixir pool manager
    if not _write(protocol_out, "READY\n"):
        return

    while True:
        try:
            header = _readline()
        except (EOFError, OSError):
            break

        if not header:
            break  # stdin closed — parent died

        header = header.strip()

        if header == "EXIT":
            break

        try:
            length = int(header)
        except ValueError:
            if not _write(protocol_out, "ERROR_START\n", f"Bad header: {header!r}\n", "ERROR_END\n"):
                break
            continue

        try:
            script_bytes = _read_exactly(length)
            script = script_bytes.decode("utf-8")
        except (EOFError, OSError):
            break
        except Exception as e:
            if not _write(protocol_out, "ERROR_START\n", f"Failed to read script: {e}\n", "ERROR_END\n"):
                break
            continue

        output, error = _run_script(script)

        if error:
            if not _write(protocol_out, "ERROR_START\n", output, error, "ERROR_END\n"):
                break
        else:
            if not _write(protocol_out, "RESULT_START\n", output, "RESULT_END\n"):
                break


if __name__ == "__main__":
    main()
