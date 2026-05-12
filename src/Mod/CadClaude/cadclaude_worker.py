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


_EXTRACT_BODY_SHAPE_FIXED = '''\
def extract_body_shape(src_doc):
    body = src_doc.getObject("Body")
    if body is None:
        for obj in src_doc.Objects:
            if getattr(obj, "TypeId", "") == "PartDesign::Body":
                body = obj
                break
    if body is not None:
        return body.Shape.copy()
    for obj in src_doc.Objects:
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and len(shape.Solids) > 0:
            return shape.copy()
    raise RuntimeError(f"No Body found in document: {src_doc.Name}")'''

_EXTRACT_BODY_SHAPE_OLD = '''\
def extract_body_shape(src_doc):
    body = src_doc.getObject("Body")
    if body is None:
        for obj in src_doc.Objects:
            if getattr(obj, "TypeId", "") == "PartDesign::Body":
                body = obj
                break
    if body is None:
        raise RuntimeError(f"No Body found in document: {src_doc.Name}")
    return body.Shape.copy()'''


_ADD_PART_FRAGILE = '''\
    if os.path.exists(fcstd_path):
            src_doc = FreeCAD.openDocument(fcstd_path)
            shape = extract_body_shape(src_doc)
            FreeCAD.closeDocument(src_doc.Name)
        elif os.path.exists(step_path):'''

_ADD_PART_ROBUST = '''\
    shape = None
        if os.path.exists(fcstd_path):
            try:
                src_doc = FreeCAD.openDocument(fcstd_path)
                shape = extract_body_shape(src_doc)
                FreeCAD.closeDocument(src_doc.Name)
            except Exception as e:
                print(f"WARN: {name} FCStd failed ({e}), falling back to STEP")
                shape = None
        if shape is None:
            if os.path.exists(step_path):'''


def _fix_common_mistakes(script_source):
    """Auto-correct known headless-incompatible patterns before execution."""
    import re

    # ImportGui is GUI-only; replace with Part for STEP export
    script_source = re.sub(r'^import ImportGui\s*$', '', script_source, flags=re.MULTILINE)
    script_source = re.sub(r'ImportGui\.export\(', 'Part.export(', script_source)

    # extract_body_shape: add direct-modeling fallback (Part::Feature, not just PartDesign::Body)
    if _EXTRACT_BODY_SHAPE_OLD in script_source:
        script_source = script_source.replace(_EXTRACT_BODY_SHAPE_OLD, _EXTRACT_BODY_SHAPE_FIXED)

    # add_part: catch FCStd extraction errors and fall back to STEP instead of crashing
    script_source = re.sub(
        r'if os\.path\.exists\(fcstd_path\):\s*\n(\s+)src_doc = FreeCAD\.openDocument\(fcstd_path\)\s*\n\s+shape = extract_body_shape\(src_doc\)\s*\n\s+FreeCAD\.closeDocument\(src_doc\.Name\)\s*\n\s+elif os\.path\.exists\(step_path\):',
        lambda m: (
            'shape = None\n'
            f'{m.group(1)}if os.path.exists(fcstd_path):\n'
            f'{m.group(1)}    try:\n'
            f'{m.group(1)}        src_doc = FreeCAD.openDocument(fcstd_path)\n'
            f'{m.group(1)}        shape = extract_body_shape(src_doc)\n'
            f'{m.group(1)}        FreeCAD.closeDocument(src_doc.Name)\n'
            f'{m.group(1)}    except Exception as e:\n'
            f'{m.group(1)}        print(f"WARN: {{name}} FCStd failed ({{e}}), falling back to STEP")\n'
            f'{m.group(1)}        shape = None\n'
            f'{m.group(1)}if shape is None:\n'
            f'{m.group(1)}    if os.path.exists(step_path):'
        ),
        script_source
    )

    return script_source


def _run_script(script_source):
    """
    Execute script_source, capturing stdout/stderr.
    Returns (output, error) where error is None on success.
    Also closes any FreeCAD documents left open by the script (cleanup
    after crashes that skip FreeCAD.closeDocument).
    """
    script_source = _fix_common_mistakes(script_source)
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

    return captured.getvalue(), error


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
