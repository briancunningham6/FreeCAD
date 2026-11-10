# Engine Version Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every FreeCAD fork install describes itself (`BUILD-INFO.json`), every worker
announces what it is actually running (`ENGINE {json}` before `READY PROTOCOL 2`), and
ElixiHub logs it, stamps it on issue reports and shows it in Settings. Two engines can then
be compared with a manifest diff.

**Architecture:** A stdlib-only Python generator, run by a CMake target on every build,
writes the manifest into the build dir. CMake installs it at the prefix root. ElixiCAD's
worker (the only worker after Task 7) reads the manifest, adds runtime facts and content
digests, and emits one `ENGINE` line before `READY`. ElixiHub parses that line during
`await_ready`, keeps the latest identity in `:persistent_term`, and exposes it through
`WorkerPool.engine_info/0`. This follows the existing `last_start_error` pattern.

**Tech Stack:** Python 3 stdlib + pytest (fork and worker), CMake, Elixir/Phoenix
LiveView + Ecto (ElixiHub).

**Spec:** `docs/superpowers/specs/2026-11-10-engine-version-tracking-design.md`

## Global Constraints

- Two repos. FreeCAD fork: `/Users/user/dev/FreeCAD`, branch `feat/engine-version-tracking`
  cut from `feat/elixifree-core`. ElixiCAD: `/Users/user/dev/ElixiCAD`, branch
  `feat/engine-version-tracking` cut from `main`.
- ElixiCAD's tree has unrelated uncommitted changes (`docs/DOC-*.md`,
  `realised_io/…`, untracked plans). **Commit only the files each task lists.** Never
  `git add -A`.
- Run Elixir commands as `env -u MIX_ENV mix …` from `/Users/user/dev/ElixiCAD/elixihub`,
  because the shell exports `MIX_ENV=dev`.
- Manifest file name and location: `<prefix>/BUILD-INFO.json`. Schema number: `1`.
- Protocol line: `ENGINE <compact json>\n`, emitted **before** `READY PROTOCOL 2\n`, at
  most **16384 bytes** including the prefix and newline. Omitted entirely on any
  collection failure.
- Sync merge subject convention, which the upstream-base lookup depends on:
  `Merge upstream FreeCAD main <sha>`. Regex: `^Merge upstream FreeCAD main ([0-9a-f]{7,40})`.
- The generator and the worker identity code **never** fail the build or block boot.
- Do not modify upstream files `src/Build/Version.h.cmake` or `src/Tools/SubWCRev.py`.
- Production install `~/freecad-cadclaude` is touched only in Task 9, after asking the user.

## Review Focus

1. **The Docker/CI build has no `.git`.** The fork's `Dockerfile` does `COPY . /src`.
   The generator must produce a valid manifest with null git facts and must not fail the
   build. Test: `test_no_git_dir_yields_null_git_facts` (Task 1).
2. **A pre-manifest install**, such as a rollback dir or a Fly image built before Task 2.
   The worker must still emit `ENGINE` with `"manifest": null`, and ElixiHub must show
   "no build manifest" rather than crashing. Tests: `test_engine_payload_without_manifest`
   (Task 3) and `summary/2 with nil manifest` (Task 5).
3. **The `ENGINE` line fragments across Port chunks**, or shares a chunk with `READY`. The
   identity must still be parsed and READY still recognised. Test:
   `"engine_info/1 across chunk boundaries"` (Task 4).
4. **A huge dirty tree**, with thousands of modified files after an upstream merge. The
   manifest caps `dirty_paths` at 50, and the line still fits in 16384 bytes. Tests:
   `test_dirty_paths_capped_at_50` (Task 1) and `test_engine_line_respects_size_cap`
   (Task 3).
5. **No elixifree tree on the worker host**, for example a release without a workspace.
   `elixifree` must be `null` without affecting the other fields. Test:
   `test_engine_payload_without_elixifree` (Task 3).

---

### Task 1: Manifest generator script (fork)

**Files:**
- Create: `scripts/gen-build-info.py`
- Test: `scripts/tests/test_gen_build_info.py`

**Interfaces:**
- Produces, as a CLI used by Task 2:
  `gen-build-info.py --srcdir <dir> --facts <facts.json> --out <BUILD-INFO.json>`. It
  exits 0 always and prints `BUILD-INFO.json: updated` or `BUILD-INFO.json: unchanged`.
- Produces these functions, importable via `importlib` because the file name has hyphens:
  - `git_facts(srcdir: str) -> dict`. Keys: `git`, `describe`, `branch`, `dirty`,
    `dirty_paths`. All values are `None` (and `dirty_paths: []`) when git or `.git` is
    absent.
  - `upstream_base(srcdir: str) -> dict`. Keys: `base`, `base_date`; `None` when no
    matching merge is found.
  - `build_manifest(facts: dict, srcdir: str, now: datetime) -> dict`. The full schema-1
    dict shown in the spec, Component 1. `facts` provides `versions`, `toolchain` and
    `options`, plus `fork`/`upstream` fields computed here.
  - `write_if_changed(manifest: dict, path: str) -> bool`. Compares everything except
    `built_at`. Writes `json.dumps(manifest, indent=2, sort_keys=True)` plus a newline.

- [ ] **Step 1: Write failing tests** in `scripts/tests/test_gen_build_info.py`. Use a
  `tmp_path` git repo fixture (`git init`, commit a file) with `subprocess`. Tests:
  - `test_clean_repo_facts`: `git` is 40 hex characters, `dirty is False`,
    `dirty_paths == []`, `branch == "main"`. Create the branch with
    `git checkout -b main`.
  - `test_dirty_repo_lists_modified_tracked_files`: modify the committed file. Expect
    `dirty is True` and `dirty_paths == ["a.txt"]`. An untracked new file must **not**
    appear (`--untracked-files=no`).
  - `test_dirty_paths_capped_at_50`: commit 60 files, modify all of them. Expect
    `len(dirty_paths) == 50` and `dirty is True`.
  - `test_detached_head_branch_is_none`: `git checkout --detach`, so `branch is None`.
  - `test_no_git_dir_yields_null_git_facts`: plain `tmp_path` with no repo. Every key is
    `None`, `dirty_paths == []`, and no exception.
  - `test_upstream_base_from_sync_merge`: create commit U on an orphan branch and a commit
    on main, then `git merge --allow-unrelated-histories -m "Merge upstream FreeCAD main <U short sha>" U`
    and add one commit after it. Expect `upstream_base(...)["base"] ==` the full sha of
    U (the merge's second parent) and `base_date` to be ISO-8601 UTC ending in `Z`.
  - `test_upstream_base_none_without_sync_merge`: expect `{"base": None, "base_date": None}`.
  - `test_write_if_changed_ignores_built_at`: the first write returns `True`. The same
    manifest with a different `built_at` returns `False` and leaves the file's mtime
    unchanged. A changed `versions.qt` returns `True`.
  - `test_cli_always_exits_zero`: run the script via `subprocess` with a nonexistent
    `--facts` path. Expect exit 0 and an output file containing an `"error"` key and
    `"schema": 1`.

- [ ] **Step 2: Run the tests to confirm they fail**
  Run: `cd /Users/user/dev/FreeCAD && python3 -m pytest scripts/tests/test_gen_build_info.py -q`
  Expected: FAIL (the module file doesn't exist).

- [ ] **Step 3: Implement `scripts/gen-build-info.py`.** Git facts:
  - `git rev-parse HEAD`
  - `git describe --tags --always`
  - `git symbolic-ref --short -q HEAD` (non-zero exit means `None`)
  - `git status --porcelain --untracked-files=no` (path = line[3:])

  Run every call with `cwd=srcdir`, a 10 s timeout and `check=False`; any `OSError` or
  non-zero exit gives `None`. For the upstream base, run
  `git log --first-parent --merges --format=%H%x00%P%x00%s` and take the first line
  whose subject matches the Global Constraints regex. The base is the second sha in `%P`,
  and its date comes from `git show -s --format=%cI <base>`, normalised to UTC `Z`.
  `built_at` is `now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`. `main()`
  wraps everything in `try/except Exception`, and on failure writes
  `{"schema": 1, "error": str(e)}`.

- [ ] **Step 4: Run the tests to confirm they pass**
  Run: `python3 -m pytest scripts/tests/test_gen_build_info.py -q`
  Expected: all 9 pass.

- [ ] **Step 5: Commit**
  ```bash
  git add scripts/gen-build-info.py scripts/tests/test_gen_build_info.py
  git commit -m "feat(build): BUILD-INFO.json manifest generator"
  ```

### Task 2: CMake wiring for the manifest (fork)

**Files:**
- Create: `cMake/build-info-facts.json.in`
- Create: `cMake/FreeCAD_Helpers/SetupBuildInfo.cmake`
- Modify: `CMakeLists.txt` (include the helper, then call `SetupBuildInfo()` immediately
  after the existing `install(PROGRAMS scripts/freecad-worker DESTINATION bin)` at about
  line 155)
- Modify: `ELIXICAD-BUILD.md` (section "5. Install": add one line saying the install
  writes `BUILD-INFO.json` and how to diff two installs:
  `diff <(jq -S . a/BUILD-INFO.json) <(jq -S . b/BUILD-INFO.json)`)

**Interfaces:**
- Consumes: the Task 1 CLI.
- Produces: `${CMAKE_BINARY_DIR}/BUILD-INFO.json` after every build, and
  `<prefix>/BUILD-INFO.json` after install. Task 3 reads the installed file.

- [ ] **Step 1: Write `cMake/build-info-facts.json.in`.** This is a JSON object with
  `versions`, `toolchain` and `options` and `@VAR@` placeholders, configured with
  `@ONLY`. The variables:

  | Field | Variable |
  |---|---|
  | `versions.freecad` | `@PACKAGE_VERSION@@PACKAGE_VERSION_SUFFIX@` |
  | `versions.occt` | `@OCC_VERSION_STRING@` plus `.@OCC_VERSION_DEVELOPMENT@` when defined. Precompute `BUILD_INFO_OCC` in the helper. |
  | `versions.python` | `@Python3_VERSION@` |
  | `versions.qt` | `@Qt6Core_VERSION@` |
  | `versions.boost` | `@Boost_VERSION@` |
  | `toolchain.platform` | `@CMAKE_SYSTEM_NAME@-@CMAKE_SYSTEM_VERSION@-@CMAKE_SYSTEM_PROCESSOR@` |
  | `toolchain.compiler` | `@CMAKE_CXX_COMPILER_ID@ @CMAKE_CXX_COMPILER_VERSION@` |
  | `toolchain.sdk` | `@BUILD_INFO_SDK@`: the basename of `CMAKE_OSX_SYSROOT`, or the JSON literal `null` when it is empty |
  | `toolchain.generator` | `@CMAKE_GENERATOR@` |
  | `toolchain.build_type` | `@CMAKE_BUILD_TYPE@` |
  | `options.modules_on` | `@BUILD_INFO_MODULES_JSON@` |
  | `options.flags` | `@BUILD_INFO_FLAGS_JSON@`: exactly `BUILD_GUI`, `OCCT_CMAKE_FALLBACK`, `ENABLE_DEVELOPER_TESTS`, `FREECAD_VERSION_INCLUDE_GIT` |
  | `options.occt_dirs` | `@OCC_INCLUDE_DIR@`, `@OCC_LIBRARY_DIR@` |

- [ ] **Step 2: Implement `SetupBuildInfo()`** in `SetupBuildInfo.cmake`:
  - Compute `BUILD_INFO_MODULES_JSON` as a sorted JSON array of names `X` for every cache
    variable `BUILD_X` that is `ON`. Exclude `BUILD_GUI`, `BUILD_TEST` and
    `BUILD_DYNAMIC_LINK_PYTHON`; use `get_cmake_property(_v CACHE_VARIABLES)`.
  - Compute `BUILD_INFO_FLAGS_JSON` and `BUILD_INFO_SDK`, then call `configure_file(...)`
    to write `${CMAKE_BINARY_DIR}/build-info-facts.json`.
  - Add `add_custom_target(fc_build_info ALL COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/scripts/gen-build-info.py --srcdir ${CMAKE_SOURCE_DIR} --facts ${CMAKE_BINARY_DIR}/build-info-facts.json --out ${CMAKE_BINARY_DIR}/BUILD-INFO.json VERBATIM)`.
  - Add `install(FILES ${CMAKE_BINARY_DIR}/BUILD-INFO.json DESTINATION .)`.

- [ ] **Step 3: Configure and build the target**
  Run: `cmake -S . -B build-sync && cmake --build build-sync --target fc_build_info && jq . build-sync/BUILD-INFO.json`
  Expected:
  - `versions.occt == "8.0.0.rc4-e72d772e70"`, `versions.qt == "6.11.1"`.
  - `toolchain.sdk == "MacOSX26.5.sdk"`.
  - `options.modules_on` contains `"Part"` and `"Sketcher"` and not `"GUI"`.
  - `fork.git` equals `git rev-parse HEAD`.
  - `upstream.base` starts with `d170797279`.

  If any field is empty, fix the variable name in the template. Check the configure log
  with `grep -n` rather than guessing.

- [ ] **Step 4: Verify that no-op builds don't rewrite the file**
  Run: `cmake --build build-sync --target fc_build_info; stat -f %m build-sync/BUILD-INFO.json; cmake --build build-sync --target fc_build_info; stat -f %m build-sync/BUILD-INFO.json`
  Expected: the two mtimes are identical, and the second run prints `BUILD-INFO.json: unchanged`.

- [ ] **Step 5: Verify install into a throwaway prefix**
  Run: `cmake --build build-sync --parallel 10 && cmake --install build-sync --prefix /private/tmp/claude-503/fc-bi-prefix && jq .fork.git /private/tmp/claude-503/fc-bi-prefix/BUILD-INFO.json`
  Expected: the HEAD sha. Then `rm -rf /private/tmp/claude-503/fc-bi-prefix`.

- [ ] **Step 6: Commit**
  ```bash
  git add cMake/build-info-facts.json.in cMake/FreeCAD_Helpers/SetupBuildInfo.cmake CMakeLists.txt ELIXICAD-BUILD.md
  git commit -m "feat(build): generate and install BUILD-INFO.json"
  ```

### Task 3: `ENGINE` line in the ElixiCAD worker

**Files:**
- Modify: `/Users/user/dev/ElixiCAD/freecad-workspace/cadclaude_worker.py`. Add the
  functions below near the existing `_elixifree_signature`, and call them in `main()`
  before the `READY PROTOCOL 2` write at about line 655. Add `import hashlib`. Update the
  module docstring's protocol block with the `ENGINE` line.
- Test: `/Users/user/dev/ElixiCAD/freecad-workspace/tests/test_cadclaude_worker_engine.py`.
  Load the worker the same way as `test_cadclaude_worker_metrics.py`
  (`importlib.util.spec_from_file_location`).

**Interfaces:**
- Consumes: the `<prefix>/BUILD-INFO.json` schema from Task 1.
- Produces, used by Task 4 and Task 5 (wire format, spec Component 2):
  `ENGINE {"schema":1,"manifest":{…}|null,"runtime":{freecad_git,freecad,occt,python,prefix,manifest_matches_binary},"worker":{path,sha256,protocol:2},"elixifree":{path,sha256,files}|null}`
- Functions:
  - `_sha256_file(path: str) -> str | None`
  - `_tree_digest(root: str) -> tuple[str, int] | None`. SHA-256 over sorted
    `(relpath, bytes)` of `*.py` under `root`, skipping `__pycache__`. Feed
    `relpath.encode() + b"\0" + content + b"\0"` per file.
  - `_runtime_facts() -> dict`. Imports FreeCAD and Part. The caller handles failure.
  - `_engine_payload(prefix: str | None = None, runtime: dict | None = None, elixifree_root: str | None = None) -> dict`.
    The parameters exist for tests. They default to `FreeCAD.getHomePath()`,
    `_runtime_facts()` and the loaded `elixifree.__path__[0]`, or
    `os.environ["ELIXIFREE_PATH"] + "/elixifree"`, whichever exists.
  - `_engine_line(payload: dict) -> str | None`. Returns `"ENGINE " + json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"`.
    If that exceeds 16384 bytes, drop `manifest.options`, then `manifest.fork.dirty_paths`,
    and return `None` if it still doesn't fit.

- [ ] **Step 1: Write failing tests:**
  - `test_tree_digest_changes_with_content`: a temp tree with two `.py` files. The digest
    is stable across two calls and `files == 2`. Editing one file changes it. A
    `__pycache__/x.py` file doesn't count.
  - `test_engine_payload_with_manifest`: write a temp `BUILD-INFO.json` with
    `fork.git = "cb497e35a3" + "0"*30`, and pass
    `runtime={"freecad_git": "cb497e35a3", …}`. Expect
    `payload["runtime"]["manifest_matches_binary"] is True`,
    `payload["manifest"]["fork"]["git"]` to be preserved, and
    `payload["worker"]["protocol"] == 2`.
  - `test_engine_payload_mismatch`: runtime `freecad_git = "aaaaaaaaaa"`, so
    `manifest_matches_binary is False`.
  - `test_engine_payload_without_manifest`: a prefix dir with no file, so
    `payload["manifest"] is None` and `manifest_matches_binary is None`.
  - `test_engine_payload_without_elixifree`: `elixifree_root` points to a nonexistent
    directory, so `payload["elixifree"] is None` and the other keys are present.
  - `test_engine_line_single_line_and_prefixed`: starts with `"ENGINE {"`, ends with
    `"\n"`, has exactly one `"\n"`, and does not contain `"READY"`.
  - `test_engine_line_respects_size_cap`: a manifest with `options` padded to 20 KB and
    50 dirty paths. The line is ≤ 16384 bytes and has no `options` key. A payload whose
    `runtime` alone is padded past 16 KB gives `None`.
  - `test_main_emits_engine_before_ready`: monkeypatch `_engine_payload` to return
    `{"schema": 1}` and `_write` to record calls. Stub the `_readline` loop with an
    immediate `""` (EOF). The first written line starts with `ENGINE ` and the next is
    `READY PROTOCOL 2\n`. With `_engine_payload` raising `RuntimeError`, the only written
    line is `READY PROTOCOL 2\n`.

- [ ] **Step 2: Run the tests to confirm they fail**
  Run: `cd /Users/user/dev/ElixiCAD && python3 -m pytest freecad-workspace/tests/test_cadclaude_worker_engine.py -q`
  Expected: FAIL (the attributes don't exist).

- [ ] **Step 3: Implement the functions above.** In `main()`, add:
  `try: line = _engine_line(_engine_payload())` with `except Exception: line = None`,
  then `if line and not _write(protocol_out, line): return`, before the READY write.

- [ ] **Step 4: Run the new test file and the existing worker tests**
  Run: `python3 -m pytest freecad-workspace/tests -q -k cadclaude_worker`
  Expected: all pass, including the 6 existing `test_cadclaude_worker_*` files.

- [ ] **Step 5: Run an end-to-end smoke against the real binary.** Use the prefix from
  Task 2 Step 5, re-installed temporarily, or `~/freecad-cadclaude`, which has no
  manifest yet; the latter exercises Review Focus #2.
  Run: `python3 -I /Users/user/dev/FreeCAD/.claude/skills/align-upstream/scripts/smoke_p2.py ~/freecad-cadclaude/bin/freecad-worker`
  The script is created in Task 8. Until then, use
  `/private/tmp/claude-503/-Users-user-dev-FreeCAD/aa2fa7d6-1648-4419-bb7b-d6195ba99484/scratchpad/worker_smoke_p2.py`
  with a `print` of any line starting with `ENGINE`.
  Expected: one `ENGINE` line whose `runtime.freecad_git == "cb497e35a3"` and whose
  `manifest` is null, then `READY PROTOCOL 2`, then `SMOKE P2: PASS`.

- [ ] **Step 6: Commit (ElixiCAD)**
  ```bash
  git add freecad-workspace/cadclaude_worker.py freecad-workspace/tests/test_cadclaude_worker_engine.py
  git commit -m "feat(worker): announce engine identity on an ENGINE line before READY"
  ```

### Task 4: ElixiHub parses and keeps the engine identity

**Files:**
- Modify: `elixihub/lib/elixihub/freecad/frames.ex` (add `engine_info/1`, and document
  `ENGINE` in the moduledoc protocol block)
- Modify: `elixihub/lib/elixihub/freecad/worker.ex`:
  - `await_ready/2` returns `{:ok, protocol, engine_info}`.
  - Update the `do_init/1` match clauses at about lines 132–137.
  - Add `engine_info/0` and `record_engine_info/1` next to `last_start_error/0`, at about
    lines 104–113.
- Modify: `elixihub/lib/elixihub/freecad/worker_pool.ex` (`defdelegate engine_info(), to: Elixihub.FreeCAD.Worker`, next to `last_start_error` at line 85)
- Modify: `elixihub/lib/elixihub/build_info.ex` (`def engine, do: Elixihub.FreeCAD.WorkerPool.engine_info()`, with `@doc`)
- Test: `elixihub/test/elixihub/freecad/frames_test.exs`
- Test (create): `elixihub/test/elixihub/freecad/worker_engine_info_test.exs`

**Interfaces:**
- Consumes: the Task 3 wire format.
- Produces:
  - `Frames.engine_info(buffer :: binary()) :: map() | nil`
  - `Worker.engine_info() :: map() | nil`, and `WorkerPool.engine_info/0`, which delegates
    to it.
  - `Worker.record_engine_info(info :: map() | nil) :: :new | :same | :changed`.
    It stores the value in `:persistent_term` under
    `{Elixihub.FreeCAD.WorkerPool, :engine_info}` **only when the value differs**, because
    every `persistent_term` write is a global GC. `nil` never overwrites a stored value.
  - `BuildInfo.engine/0`.

- [ ] **Step 1: Write failing tests:**
  - In `frames_test.exs`:
    - `"engine_info/1 decodes the ENGINE line"`:
      `Frames.engine_info(~s(ENGINE {"schema":1}\nREADY PROTOCOL 2\n)) == %{"schema" => 1}`.
    - `"engine_info/1 returns nil without an ENGINE line or on bad JSON"`: test
      `"READY PROTOCOL 2\n"` and `"ENGINE {nope\nREADY PROTOCOL 2\n"`.
    - `"engine_info/1 across chunk boundaries"`: `ready?/1` gives `:incomplete` on
      `~s(ENGINE {"sch)`. On the concatenated
      `~s(ENGINE {"sch) <> ~s(ema":1}\nREADY PROTOCOL 2\n)`, `ready?/1` gives `{:ok, 2}`
      and `engine_info/1` gives `%{"schema" => 1}`.
    - `"ready?/1 is not fooled by ENGINE alone"`:
      `Frames.ready?(~s(ENGINE {"a":"READY"}\n)) == :incomplete`.
  - In `worker_engine_info_test.exs` (`async: false`; erase the persistent_term key in
    `setup` and `on_exit`):
    - The first `record_engine_info(%{"a" => 1})` gives `:new`, and
      `Worker.engine_info() == %{"a" => 1}`.
    - The same value again gives `:same`.
    - A different value gives `:changed`, and `capture_log` contains
      `"FreeCAD engine changed"` with both short shas taken from
      `["manifest"]["fork"]["git"]` (first 10 characters) or
      `["runtime"]["freecad_git"]`.
    - `record_engine_info(nil)` gives `:same` and leaves the stored value intact.

- [ ] **Step 2: Run the tests to confirm they fail**
  Run: `cd /Users/user/dev/ElixiCAD/elixihub && env -u MIX_ENV mix test test/elixihub/freecad/frames_test.exs test/elixihub/freecad/worker_engine_info_test.exs`
  Expected: FAIL (undefined functions).

- [ ] **Step 3: Implement.**
  - `engine_info/1` uses `:binary.match` for `"ENGINE "`, then `:binary.match` for `"\n"`
    after it, then `Jason.decode`. Return `nil` on any miss or error.
  - Return a map only, never a list or scalar: a `%{}` guard on the decode result.
  - In `do_init`, on `{:ok, 2, info}`, call `record_engine_info(info)`. Extend the
    existing `Logger.info` to
    `"FreeCAD worker ready (OS PID #{os_pid}, protocol 2, engine #{short})"`, where
    `short` is `"<git10> <freecad> occt <occt>"` or `"unknown"`.
  - `{:ok, 1, _}` keeps today's `:protocol_mismatch` path.

- [ ] **Step 4: Run the FreeCAD test directory**
  Run: `env -u MIX_ENV mix test test/elixihub/freecad`
  Expected: all pass, including `worker_protocol_test.exs`, which exercises `await_ready`.
  Update its pattern matches to the 3-tuple only where they match `await_ready` results.

- [ ] **Step 5: Commit (ElixiCAD)**
  ```bash
  git add elixihub/lib/elixihub/freecad/frames.ex elixihub/lib/elixihub/freecad/worker.ex elixihub/lib/elixihub/freecad/worker_pool.ex elixihub/lib/elixihub/build_info.ex elixihub/test/elixihub/freecad/frames_test.exs elixihub/test/elixihub/freecad/worker_engine_info_test.exs elixihub/test/elixihub/freecad/worker_protocol_test.exs
  git commit -m "feat(freecad): parse and keep the worker's ENGINE identity"
  ```

### Task 5: Engine summary, warnings and issue-report stamp

**Files:**
- Create: `elixihub/lib/elixihub/freecad/engine_info.ex`
- Create: `elixihub/priv/repo/migrations/20261110120000_add_engine_to_issue_reports.exs`
  (`alter table(:issue_reports), do: add(:engine, :map)`)
- Modify: `elixihub/lib/elixihub/issue_reports/report.ex` (add `field :engine, :map`, and
  add `:engine` to the changeset's `cast` list)
- Modify: `elixihub/lib/elixihub/issue_reports.ex:161-162` (add
  `engine: EngineInfo.stamp(BuildInfo.engine())`)
- Test (create): `elixihub/test/elixihub/freecad/engine_info_test.exs`
- Test: `elixihub/test/elixihub/issue_reports_test.exs`

**Interfaces:**
- Consumes: `BuildInfo.engine/0` (Task 4).
- Produces, used by Task 6:
  - `EngineInfo.summary(info :: map() | nil, local_worker_sha :: String.t() | nil) :: map() | nil`.
    Returns `nil` for `nil` info; otherwise
    `%{fork_git, fork_git_short, upstream_base_short, freecad, occt, python, qt, sdk, built_at, dirty?, worker_sha_short, elixifree_sha_short, warnings}`.
    Values come from the manifest when present, falling back to `runtime` for
    `freecad`/`occt`/`python`.
  - `warnings` is a list, in this order, of `:no_manifest`, `:dirty`,
    `:manifest_mismatch` (`manifest_matches_binary == false`) and `:worker_drift`
    (`local_worker_sha` non-nil and `!= worker.sha256`).
  - `EngineInfo.stamp(info :: map() | nil) :: map() | nil`, a string-keyed map containing
    exactly `"fork_git"`, `"upstream_base"`, `"freecad"`, `"occt"`, `"python"`,
    `"dirty"`, `"worker_sha256"` and `"elixifree_sha256"`.
  - `EngineInfo.local_worker_sha() :: String.t() | nil`, the SHA-256 (lowercase hex) of
    `Path.join(ElixifreeSource.path(), "cadclaude_worker.py")`, or `nil` if the file is
    missing.

- [ ] **Step 1: Write failing tests** in `engine_info_test.exs`. Build fixtures from the
  spec's example payload.
  - `summary/2 with nil manifest` gives `warnings == [:no_manifest]`, takes `freecad`
    from runtime, and has `fork_git == nil`.
  - A full payload with `dirty: true` gives `[:dirty]`.
  - `manifest_matches_binary: false` gives `:manifest_mismatch` in the warnings.
  - A local sha different from `worker.sha256` gives `:worker_drift`. An equal sha or
    `nil` gives none.
  - `stamp/1` returns exactly the 8 keys listed, and `stamp(nil) == nil`.
  - In `issue_reports_test.exs`: put a payload via
    `Elixihub.FreeCAD.Worker.record_engine_info/1` (erase the key in `on_exit`), create a
    report through the existing helper, and check that it has
    `report.engine["fork_git"] == <sha>`. With no engine recorded, `report.engine == nil`.

- [ ] **Step 2: Run the tests to confirm they fail**
  Run: `env -u MIX_ENV mix test test/elixihub/freecad/engine_info_test.exs test/elixihub/issue_reports_test.exs`
  Expected: FAIL.

- [ ] **Step 3: Implement the module, migration, schema field and stamp.**

- [ ] **Step 4: Migrate and run the tests**
  Run: `env -u MIX_ENV mix ecto.migrate && env -u MIX_ENV mix test test/elixihub/freecad/engine_info_test.exs test/elixihub/issue_reports_test.exs`
  Expected: all pass.

- [ ] **Step 5: Commit (ElixiCAD)**
  ```bash
  git add elixihub/lib/elixihub/freecad/engine_info.ex elixihub/priv/repo/migrations/20261110120000_add_engine_to_issue_reports.exs elixihub/lib/elixihub/issue_reports/report.ex elixihub/lib/elixihub/issue_reports.ex elixihub/test/elixihub/freecad/engine_info_test.exs elixihub/test/elixihub/issue_reports_test.exs
  git commit -m "feat(freecad): engine summary/warnings; stamp engine on issue reports"
  ```

### Task 6: "FreeCAD engine" section in Settings

**Files:**
- Modify: `elixihub/lib/elixihub_web/live/settings_live/show.ex`:
  - In `mount/3`, assign `:engine` to
    `EngineInfo.summary(BuildInfo.engine(), EngineInfo.local_worker_sha())` when `admin?`,
    else `nil`.
  - Add `<section :if={@admin} id="engine">` directly after the `id="compute"` section,
    at about line 166.
  - Add a matching entry in the UI-028 section list.
  - Add a private `engine_panel/1` component, styled after `macmini_panel/1`'s `<dl>`
    rows.
- Test: `elixihub/test/elixihub_web/live/settings_live/show_test.exs`

**Interfaces:**
- Consumes: `EngineInfo.summary/2` and `EngineInfo.local_worker_sha/0` (Task 5), and
  `BuildInfo.engine/0` (Task 4).

Copy (wrap every string in `gettext`):
- Heading: `FreeCAD engine`.
- Rows: `Fork commit`, `Upstream base`, `FreeCAD`, `OCCT`, `Python`, `Qt`, `SDK`,
  `Built`, `Worker script`, `elixifree`.
- Fork commit links to `https://github.com/briancunningham6/FreeCAD/commit/<fork_git>`
  and displays `fork_git_short`.
- Empty state: `No FreeCAD worker has reported its engine yet.`
- Warning text, shown in the `text-warning-role text-xs` style used at `show.ex:315`:
  - `:no_manifest`: `This install has no BUILD-INFO.json (built before engine tracking).`
  - `:dirty`: `Built from a tree with uncommitted changes.`
  - `:manifest_mismatch`: `BUILD-INFO.json does not match the running binary.`
  - `:worker_drift`: `The running worker script differs from this checkout's freecad-workspace/cadclaude_worker.py.`

- [ ] **Step 1: Write failing LiveView tests** in `show_test.exs`, using the existing
  admin login helper the file already uses:
  - With `record_engine_info/1` called on a fixture (erase the key in `on_exit`), the admin
    page has `#engine`, `"FreeCAD engine"`, the short sha, and an `href` containing
    `/commit/<full sha>`.
  - With a `dirty: true` fixture, the page contains
    `"Built from a tree with uncommitted changes."`.
  - With no engine recorded, the page contains
    `"No FreeCAD worker has reported its engine yet."`.
  - As a non-admin, there is no `#engine` element.

- [ ] **Step 2: Run the tests to confirm they fail**
  Run: `env -u MIX_ENV mix test test/elixihub_web/live/settings_live/show_test.exs`
  Expected: the new tests fail.

- [ ] **Step 3: Implement the section and component.**

- [ ] **Step 4: Run the tests and the precommit checks**
  Run: `env -u MIX_ENV mix test test/elixihub_web/live/settings_live/show_test.exs && env -u MIX_ENV mix compile --warnings-as-errors`
  Expected: all pass, with no warnings.

- [ ] **Step 5: Commit (ElixiCAD)**
  ```bash
  git add elixihub/lib/elixihub_web/live/settings_live/show.ex elixihub/test/elixihub_web/live/settings_live/show_test.exs
  git commit -m "feat(settings): show the running FreeCAD engine and its warnings"
  ```

### Task 7: One worker script (fork)

**Files:**
- Replace: `src/Mod/CadClaude/cadclaude_worker.py`. It becomes a symlink to
  `/Users/user/dev/ElixiCAD/freecad-workspace/cadclaude_worker.py`, absolute like the
  existing `src/Mod/CadClaude/elixifree` link.
- Delete: `src/Mod/CadClaude/tests/test_worker_protocol.py`, and the directory if it is
  then empty apart from `__pycache__`.
- Modify: `src/Mod/CadClaude/CMakeLists.txt`. Only if Step 3 shows the installed file is
  a copy rather than a link: move `cadclaude_worker.py` out of `CadClaude_Scripts` into
  an `install(CODE "file(CREATE_LINK …)")` rule pointing at the same absolute target.

**Interfaces:**
- Consumes: Task 3's worker, which must be committed first.

- [ ] **Step 1: Confirm nothing in the fork's copy is lost**
  Run: `cd /Users/user/dev && diff <(grep -o '^def [a-z_]*' FreeCAD/src/Mod/CadClaude/cadclaude_worker.py | sort) <(grep -o '^def [a-z_]*' ElixiCAD/freecad-workspace/cadclaude_worker.py | sort) | grep '^<'`
  Expected: only `< def _collect_build_info` and `< def _ready_line`, which Task 3
  replaces. Stop and report if anything else appears.

- [ ] **Step 2: Replace the file with the symlink and delete the protocol-1 test**
  Run: `git rm src/Mod/CadClaude/tests/test_worker_protocol.py && rm src/Mod/CadClaude/cadclaude_worker.py && ln -s /Users/user/dev/ElixiCAD/freecad-workspace/cadclaude_worker.py src/Mod/CadClaude/cadclaude_worker.py && git add src/Mod/CadClaude/cadclaude_worker.py`
  Expected: `git diff --cached --summary` shows `mode change 100644 => 120000`, or a
  typechange.

- [ ] **Step 3: Verify install into a throwaway prefix**
  Run: `cmake --install build-sync --prefix /private/tmp/claude-503/fc-wk-prefix && ls -la /private/tmp/claude-503/fc-wk-prefix/Mod/CadClaude/`
  Expected: `cadclaude_worker.py -> /Users/user/dev/ElixiCAD/freecad-workspace/cadclaude_worker.py`.
  If it's a plain copy, apply the `CMakeLists.txt` change above and repeat.

- [ ] **Step 4: Verify the launcher's default path, with no `FREECAD_WORKER_PY`**
  Run: `env -u FREECAD_WORKER_PY python3 -I <smoke_p2.py> /private/tmp/claude-503/fc-wk-prefix/bin/freecad-worker`.
  Use a smoke variant that doesn't set `FREECAD_WORKER_PY`: `smoke_p2.py --no-worker-env`
  from Task 8, or temporarily drop the `env.update` line in the scratch copy.
  Expected: `READY PROTOCOL 2` and `SMOKE P2: PASS`. Then
  `rm -rf /private/tmp/claude-503/fc-wk-prefix`.

- [ ] **Step 5: Commit**
  ```bash
  git commit -m "refactor(cadclaude): use ElixiCAD's worker as the only worker (symlink, like elixifree)"
  ```

### Task 8: align-upstream skill and harness scripts (fork)

**Files:**
- Create: `.claude/skills/align-upstream/scripts/run-suites.sh`. Promote it from
  `/private/tmp/claude-503/-Users-user-dev-FreeCAD/aa2fa7d6-1648-4419-bb7b-d6195ba99484/scratchpad/run-suites.sh`.
  Make the scratchpad `OUT` a third argument `<outdir>`. Also have it produce the
  `<label>-<suite>-v.txt` per-test lists, using the exact `grep`/`sed` pipeline from that
  session: per-test `-v` result lines plus `ERROR collecting` headers, `sort -u`.
- Create: `.claude/skills/align-upstream/scripts/smoke_p2.py`. Promote it from the
  scratchpad `worker_smoke_p2.py`. Add `--no-worker-env`, print the `ENGINE` line if
  present, and add `--expect-git <sha10>`, which fails unless
  `ENGINE.runtime.freecad_git` equals it.
- Modify: `.claude/skills/align-upstream/SKILL.md`

**Interfaces:**
- Consumes: Task 2's manifest and Task 3's `ENGINE` line.

- [ ] **Step 1: Promote both scripts with the changes above.** `chmod +x run-suites.sh`.

- [ ] **Step 2: Verify the scripts against production**
  Run: `.claude/skills/align-upstream/scripts/run-suites.sh ~/freecad-cadclaude/MacOS/FreeCADCmd check /private/tmp/claude-503/as-check && wc -l /private/tmp/claude-503/as-check/check-*-v.txt`
  Expected: 232 elixifree and 210 elixicad lines (the 2026-11-10 baseline). Small drift
  is fine if ElixiCAD has moved; note it.
  Run: `python3 -I .claude/skills/align-upstream/scripts/smoke_p2.py ~/freecad-cadclaude/bin/freecad-worker --expect-git cb497e35a3`
  Expected: `SMOKE P2: PASS`.

- [ ] **Step 3: Edit `SKILL.md`:**
  - **Hard rules:** add a bullet:
    `Sync merge subject is exactly "Merge upstream FreeCAD main <sha>" — BUILD-INFO.json derives upstream.base from it.`
  - **Process step 1 (Preflight):** save `~/freecad-cadclaude/BUILD-INFO.json`
    (if present) and the production `ENGINE` line. Run baselines with
    `scripts/run-suites.sh <bin> baseline <outdir>`.
  - **Process step 5 (Gates):** replace the "Worker smoke" bullet with
    `scripts/smoke_p2.py <sync-prefix>/bin/freecad-worker --expect-git <built sha10>`.
    It drives ElixiCAD's worker as ElixiHub does, using `FREECAD_WORKER_PY` and
    `ELIXIFREE_PATH`. Replace the elixifree and ElixiCAD parity bullets with
    `diff <outdir>/baseline-<suite>-v.txt <outdir>/sync-<suite>-v.txt`.
  - **Process step 7 (Swap):** checkpoint 2's question includes
    `diff <(jq -S . old/BUILD-INFO.json) <(jq -S . new/BUILD-INFO.json)`.
    Re-run `smoke_p2.py --expect-git` against the production path.
  - **Gotchas table:** add rows for:
    - `FreeCADCmd` needing `DYLD_LIBRARY_PATH` (rpath is only `/usr/local/lib`).
    - FreeCAD's exit truncating pytest's short summary.
    - `ElixiCAD/.claude/worktrees` polluting collection.
    - The fork's worker not being what ElixiHub runs.
    - The CommandLineTools SDK disappearing (check `<sdk>/usr/lib/libz.tbd`).
  - Delete the "Runtime shifts ride along invisibly" row's manual counter and point it at
    the manifest diff.

- [ ] **Step 4: Commit**
  ```bash
  git add .claude/skills/align-upstream/scripts/run-suites.sh .claude/skills/align-upstream/scripts/smoke_p2.py .claude/skills/align-upstream/SKILL.md
  git commit -m "feat(align-upstream): manifest diff, protocol-2 smoke, reusable parity harness"
  ```

### Task 9: Roll out and verify end to end

**Files:** none. This task is deployment and verification only.

- [ ] **Step 1: Run the full ElixiHub test suite and the worker tests**
  Run: `cd /Users/user/dev/ElixiCAD/elixihub && env -u MIX_ENV mix test`, then
  `cd .. && python3 -m pytest freecad-workspace/tests -q`
  Expected: no new failures compared with `main`. Diff the failure lists against a `main`
  run if the suite has pre-existing failures.

- [ ] **Step 2: Ask the user before touching production.** Ask them to approve:
  - installing the rebuilt fork (with the manifest and the worker symlink) into
    `~/freecad-cadclaude`,
  - restarting the ElixiHub worker pool.

  Rollback is `~/freecad-cadclaude-pre-sync-2026-11-10` or a fresh `cmake --install` from
  `main`.

- [ ] **Step 3: Install into production and verify**
  Run: `cd /Users/user/dev/FreeCAD && cmake --build build-sync --parallel 10 && cmake --install build-sync --prefix ~/freecad-cadclaude && jq '{git:.fork.git, base:.upstream.base, sdk:.toolchain.sdk}' ~/freecad-cadclaude/BUILD-INFO.json && python3 -I .claude/skills/align-upstream/scripts/smoke_p2.py ~/freecad-cadclaude/bin/freecad-worker --expect-git $(git rev-parse --short=10 HEAD)`
  Expected: the manifest fields are populated and `SMOKE P2: PASS`. The `ENGINE` line has
  `manifest_matches_binary: true`.

- [ ] **Step 4: Check ElixiHub after the user restarts the pool (or with permission)**
  Expected:
  - The log shows `FreeCAD worker ready (OS PID …, protocol 2, engine <sha10> 27.1.0 occt 8.0.0.rc4…)`.
  - Settings → FreeCAD engine shows the same commit and no warnings.
  - A new test issue report has `engine.fork_git` set.

- [ ] **Step 5: Update the memory note** `upstream-sync-2026-11.md`. Engine tracking is
  live. The sync procedure now uses the manifest diff and `smoke_p2.py`.
