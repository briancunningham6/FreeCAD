"""
cadclaude_worker.py — Persistent FreeCAD worker for ElixiCad.

Protocol (over stdin/stdout, all messages newline-terminated):
  Startup:     worker emits  "READY\\n"
  Per request:
    Elixir -> worker:  "<length>\\n<script bytes>"
    worker -> Elixir:  "RESULT_START\\n<stdout lines>\\nRESULT_END\\n"
                    or "ERROR_START\\n<traceback>\\nERROR_END\\n"
  Shutdown:    Elixir -> worker: "EXIT\\n"
               worker exits cleanly

IMPORTANT: The Elixir Worker port must NOT use :stderr_to_stdout.
If it does, fd 1 and fd 2 are already the same pipe and the
_setup_protocol_channel() redirect below is a no-op, allowing
FreeCAD's C-level Console.PrintMessage() output to corrupt the stream.
"""

import sys
import os
import traceback
import io


def _setup_protocol_channel():
    """
    Redirect OS-level fd 1 (C printf / FreeCAD.Console.PrintMessage) to
    stderr so FreeCAD/OCCT internals cannot corrupt the protocol stream.
    Returns a dedicated file object that writes to the original stdout pipe.

    After this call:
      - C-level printf/PrintMessage  -> fd 1 -> fd 2 (stderr, discarded)
      - Python print() in scripts    -> captured via StringIO in _run_script
      - Protocol traffic             -> protocol_out -> saved fd -> Elixir pipe
    """
    sys.stdout.flush()

    # Duplicate the real Elixir stdout pipe before we redirect it
    protocol_fd = os.dup(sys.stdout.fileno())
    os.set_inheritable(protocol_fd, False)

    # Point fd 1 -> fd 2 so C-level output goes to stderr instead
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

    return os.fdopen(protocol_fd, "w", buffering=1)


def _read_exactly(n):
    """Read exactly n bytes from stdin, blocking until available."""
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            raise EOFError("stdin closed while reading script body")
        buf += chunk
    return buf


def _cleanup_documents():
    """Close any FreeCAD documents left open by the previous script."""
    try:
        import FreeCAD
        for name in list(FreeCAD.listDocuments().keys()):
            try:
                FreeCAD.closeDocument(name)
            except Exception:
                pass
    except Exception:
        pass


def _run_script(script_source):
    """
    Execute script_source in a fresh namespace, capturing all Python-level
    stdout/stderr output. Returns (output, error) where error is None on success.
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured = io.StringIO()
    sys.stdout = captured
    sys.stderr = captured

    try:
        exec(compile(script_source, "<cadclaude>", "exec"), {})
        error = None
    except SystemExit:
        # Scripts end with sys.exit(0) as their normal exit — treat as clean
        error = None
    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    _cleanup_documents()

    return captured.getvalue(), error


def main():
    # Redirect C-level stdout before emitting READY so no FreeCAD/OCCT startup
    # noise can reach the Elixir protocol pipe after this point.
    protocol_out = _setup_protocol_channel()

    protocol_out.write("READY\n")
    protocol_out.flush()

    while True:
        header = sys.stdin.readline()
        if not header:
            break  # stdin closed — parent process died

        header = header.strip()

        if header == "EXIT":
            break

        try:
            length = int(header)
        except ValueError:
            protocol_out.write("ERROR_START\n")
            protocol_out.write(f"Bad header: {header!r}\n")
            protocol_out.write("ERROR_END\n")
            protocol_out.flush()
            continue

        try:
            script_bytes = _read_exactly(length)
            script = script_bytes.decode("utf-8")
        except Exception as e:
            protocol_out.write("ERROR_START\n")
            protocol_out.write(f"Failed to read script: {e}\n")
            protocol_out.write("ERROR_END\n")
            protocol_out.flush()
            continue

        output, error = _run_script(script)

        if error:
            protocol_out.write("ERROR_START\n")
            protocol_out.write(output)
            protocol_out.write(error)
            protocol_out.write("ERROR_END\n")
        else:
            protocol_out.write("RESULT_START\n")
            protocol_out.write(output)
            protocol_out.write("RESULT_END\n")

        protocol_out.flush()


if __name__ == "__main__":
    main()
