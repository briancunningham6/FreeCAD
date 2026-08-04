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
import re
import traceback
import io
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


_ADD_TO_DOC_ATTRIBUTE_ERROR = re.compile(
    r"AttributeError: '[\w.]+' object has no attribute 'add_to_doc'"
)


def _rewrite_add_to_doc_call(script_source, traceback_text):
    """
    Rewrite `<var>.add_to_doc(<args>)` to `add_to_doc(<var>, <args>)` for the
    exact call that raised the AttributeError, if any.

    `add_to_doc` is a free function in elixifree's flat primitives API (for
    plain Part.Shape/Part.Compound results), but ComponentBuilder subclasses
    (BuildResult, ConstructionResult) expose a genuine `.add_to_doc()` method —
    an LLM generating a script against the flat API can plausibly confuse the
    two conventions, since both are common in scripts it has seen. We only
    rewrite after the ORIGINAL call has already failed with exactly this
    AttributeError, so a working `.add_to_doc()` call on a real builder result
    is never touched.

    Returns the rewritten source, or None if no matching call/line was found
    (caller should surface the original error unchanged).
    """
    if not _ADD_TO_DOC_ATTRIBUTE_ERROR.search(traceback_text):
        return None

    # The failing call is always the LAST <cadclaude> frame (the actual call
    # site) — a script that calls a helper function before crashing would have
    # an earlier frame too, and only the last one is the add_to_doc() call.
    line_matches = re.findall(r'File "<cadclaude>", line (\d+)', traceback_text)
    if not line_matches:
        return None

    line_no = int(line_matches[-1])
    lines = script_source.split("\n")
    if not (1 <= line_no <= len(lines)):
        return None

    call_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\.add_to_doc\(", lines[line_no - 1])
    if not call_match:
        return None

    var_name = call_match.group(1)
    rewritten_line = re.sub(
        rf"\b{re.escape(var_name)}\.add_to_doc\(",
        f"add_to_doc({var_name}, ",
        lines[line_no - 1],
        count=1,
    )
    if rewritten_line == lines[line_no - 1]:
        return None

    lines[line_no - 1] = rewritten_line
    return "\n".join(lines)


def _fix_common_mistakes(script_source):
    """Auto-correct known headless-incompatible patterns before execution."""
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


def _exec_once(script_source):
    """Execute script_source once, capturing stdout/stderr. Returns (output, error)."""
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


def _close_open_documents():
    """Close any FreeCAD documents left open by a script (e.g. after a crash)."""
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
    Execute script_source, capturing stdout/stderr.
    Returns (output, error) where error is None on success.
    Also closes any FreeCAD documents left open by the script (cleanup
    after crashes that skip FreeCAD.closeDocument).

    If the first attempt fails with the specific mistake of calling
    `<var>.add_to_doc(...)` on a plain Part.Shape/Part.Compound (elixifree's
    flat API only exposes `add_to_doc` as a free function; only
    ComponentBuilder results like BuildResult/ConstructionResult have a real
    `.add_to_doc()` method), the offending line is rewritten and the script is
    retried once from scratch. See _rewrite_add_to_doc_call for why this must
    happen after the failure, not as a source-level pre-pass.
    """
    script_source = _fix_common_mistakes(script_source)
    output, error = _exec_once(script_source)

    if error is not None:
        rewritten = _rewrite_add_to_doc_call(script_source, error)
        if rewritten is not None:
            _close_open_documents()
            output, error = _exec_once(rewritten)

    _close_open_documents()
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


def _configure_elixifree_path(env=None):
    """
    Prepend ELIXIFREE_PATH (the launching server's freecad-workspace) to
    sys.path so `import elixifree` resolves to that checkout rather than
    whatever globally-installed copy the interpreter would otherwise find.
    ISSUE-008: a stale editable install shadowed the server's own builders,
    making skill-promised classes unimportable. Returns the inserted path,
    or None when the variable is unset or does not hold an elixifree package.
    """
    env = os.environ if env is None else env
    path = env.get("ELIXIFREE_PATH")
    if path and os.path.isdir(os.path.join(path, "elixifree")):
        sys.path.insert(0, path)
        return path
    return None


def _announce_elixifree_source():
    """Log (stderr, the noise channel) which elixifree the worker will execute."""
    try:
        import elixifree

        sys.stderr.write(
            "cadclaude_worker: elixifree from %s\n" % os.path.dirname(elixifree.__file__)
        )
    except Exception as exc:  # noqa: BLE001 — diagnostic only, never fatal
        sys.stderr.write("cadclaude_worker: elixifree unavailable: %s\n" % exc)


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


def main():
    protocol_out = _redirect_freecad_noise()

    _configure_elixifree_path()
    _announce_elixifree_source()

    # Signal readiness to the Elixir pool manager, with build identity
    # (design spec 2026-08-04); falls back to bare READY on any failure.
    if not _write(protocol_out, _ready_line(_collect_build_info())):
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
