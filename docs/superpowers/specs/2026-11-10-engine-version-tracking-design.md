# FreeCAD Engine Version Tracking — Design

**Date:** 2026-11-10
**Status:** Draft, awaiting review
**Supersedes:** the protocol and ElixiHub parts of `2026-08-04-build-identity-design.md`
**Repos touched:** FreeCAD fork (`/Users/user/dev/FreeCAD`), ElixiCAD (`/Users/user/dev/ElixiCAD`: `freecad-workspace/`, `elixihub/`)

## Purpose

When the fork is synced with upstream, or rebuilt, or patched, we need to answer two
questions reliably and without booting anything by hand:

1. **Which engine is running?** (In ElixiHub, on an issue report, in a log line.)
2. **What changed between two engines?** (Old prod vs new prod after a sync.)

Today neither is answerable. Problems seen in the 2026-11-10 sync:

| # | Gap | Evidence |
|---|---|---|
| G1 | No identity reaches ElixiHub. The 2026-08 design was only half built: the fork's worker emits `READY {json}`, but ElixiHub never runs that worker (see G2), and the ElixiHub half (`build_info` parsing, `WorkerPool.build_info/0`, settings section) was never implemented. | `git log -S build_info` in ElixiCAD finds nothing. |
| G2 | Two worker scripts have drifted apart. ElixiHub runs `ElixiCAD/freecad-workspace/cadclaude_worker.py` (protocol 2): `ElixifreeSource.worker_env/0` sets `FREECAD_WORKER_PY` on macOS, and `Dockerfile:114` copies it over the fork's file in the Fly image. The fork's `src/Mod/CadClaude/cadclaude_worker.py` (protocol 1) is dead code that diverged. | Prod held a Sep 29 hot-patch of the fork's copy that had silently dropped the build-identity code. |
| G3 | Post-build changes are invisible. The embedded hash identifies a commit, not the files actually executing. Python copied into `<prefix>/Mod/` after install, or a dirty tree at build time, is undetectable. | The Sep 29 hot-patch carried no identity at all. |
| G4 | Toolchain/dependency drift isn't recorded. The SDK moved MacOSX15.4 → 26.5 this sync; nothing captured it. Qt, Boost, compiler, build flags are likewise unrecorded. | Found only because configure failed. |
| G5 | An install directory doesn't say what it is. `~/freecad-cadclaude-pre-sync-*` rollback dirs can only be identified by booting them with a hand-built `DYLD_LIBRARY_PATH`. | — |
| G6 | `branch` is noisy and checkout-dependent (`feat/elixifree-core,upstream/HEAD` vs `feat/elixifree-core` for the same tree). | SubWCRev's `namebranchbyparents`. |

Note on the 2026-08 protocol: `READY {json}\n` is **not** accepted by today's ElixiHub.
`Frames.ready?/1` only matches `"READY PROTOCOL 2\n"` or `"READY\n"`, so a payload on the
READY line makes the hub wait until `@ready_timeout`. This design therefore puts identity
on a separate line.

## Decision summary

- **Two layers of identity:**
  - **Build manifest** (static, from the build): `BUILD-INFO.json` at the install root.
    It answers "what is this install?" without booting it (G4, G5).
  - **Runtime identity** (from the running worker): manifest + what the process actually
    loaded. It answers "what is running?" (G1, G3).
- **One worker script.** ElixiCAD's `freecad-workspace/cadclaude_worker.py` becomes the
  only worker. The fork stops carrying its own copy (G2).
- **Identity travels on its own protocol line.** `ENGINE {json}\n` is sent *before*
  `READY PROTOCOL 2\n`, so old hubs ignore it and no protocol bump is needed.
- **Comparing two engines is a manifest diff.** The align-upstream skill diffs old and new
  `BUILD-INFO.json` instead of hand-collecting versions.
- Out of scope: persisted deployment history (open question Q1), and peer and remote-worker
  identity in the hybrid dispatcher (Q2).

## Component 1: Build manifest (FreeCAD fork)

### What

`<prefix>/BUILD-INFO.json`, written at **build** time into the build dir and installed to the
prefix root. Build time, not install time, matters: the tree checked out at
`cmake --install` can differ from the one that was compiled. That happened in this sync,
where branch switching between build and install touched 4,771 files.

```json
{
  "schema": 1,
  "built_at": "2026-11-10T16:06:07Z",
  "fork": {
    "git": "cb497e35a3c1…",              // full sha
    "describe": "weekly-2026.11.04-87-gcb497e35a3",
    "branch": "feat/elixifree-core",     // `git symbolic-ref --short HEAD`, null if detached
    "dirty": false,                      // tracked files modified at build time
    "dirty_paths": []                    // capped at 50
  },
  "upstream": {
    "base": "d170797279b3…",             // see "Upstream base" below; null if unknown
    "base_date": "2026-11-10T14:00:07Z"
  },
  "versions": {
    "freecad": "27.1.0dev",
    "occt": "8.0.0.rc4-e72d772e70",
    "python": "3.13.5",
    "qt": "6.11.1",
    "boost": "1.90.0"
  },
  "toolchain": {
    "platform": "Darwin-26.6-arm64",
    "compiler": "AppleClang 17.x",
    "sdk": "MacOSX26.5.sdk",             // basename of CMAKE_OSX_SYSROOT; null on Linux
    "generator": "Unix Makefiles",
    "build_type": "Release"
  },
  "options": {
    "modules_on": ["Material", "Part", "PartDesign", "Sketcher"],
    "flags": { "BUILD_GUI": "OFF", "OCCT_CMAKE_FALLBACK": "ON", "ENABLE_DEVELOPER_TESTS": "OFF" },
    "occt_dirs": { "include": "/Users/user/dev/OCCT/install/include/opencascade",
                   "lib": "/Users/user/dev/OCCT/install/lib" }
  }
}
```

### How

- **Generator:** `scripts/gen-build-info.py`, stdlib only, run by `${Python3_EXECUTABLE}`.
  CMake passes configure-time facts as arguments (versions, sysroot, generator, the
  `BUILD_*` cache values). The script adds the git facts and the timestamp.
- **Target:** a custom target `fc_build_info` in `ALL` that always runs, the same pattern
  as the existing `fc_version` in `src/Build/CMakeLists.txt`. It writes `BUILD-INFO.json.out`
  and then `copy_if_different` to `BUILD-INFO.json`, so an unchanged manifest causes no
  relinks. `built_at` is excluded from the comparison so a no-op build doesn't rewrite it.
- **Install:** `install(FILES ${CMAKE_BINARY_DIR}/BUILD-INFO.json DESTINATION .)` next to the
  existing `freecad-worker` install rule in the root `CMakeLists.txt`.
- **Upstream base:** don't depend on an `upstream` remote, because CI and Docker checkouts
  don't have one. Use the sync merge convention instead: find the newest first-parent
  ancestor whose subject matches `^Merge upstream FreeCAD main [0-9a-f]{7,}` and take its
  second parent. This works in any full clone. If the history is shallow or no match is
  found, emit `null`. The align-upstream skill already writes merges in that form, so it
  only needs to keep doing so (added as a hard rule).
- **Failure policy:** the generator never fails the build. On any error it writes a
  manifest containing what it has plus `"error": "<message>"`.

### Not changed

FreeCAD's own `Version.h` and `SubWCRev.py` stay untouched. They're upstream code, and
touching them adds a conflict surface on every sync. G6 is fixed by the manifest's
`branch` field, not by patching SubWCRev.

## Component 2: Runtime identity (ElixiCAD worker)

### Protocol

```
ENGINE {"schema":1,…}\n        ← new, optional, single line, ≤ 16 KB
READY PROTOCOL 2\n             ← unchanged
```

- **Compatibility:** `Worker.await_ready/2` accumulates the buffer, and `Frames.ready?/1`
  matches `READY PROTOCOL 2\n` *anywhere* in it, then discards the buffer. A line sent
  earlier is therefore ignored by every existing hub. Compact JSON contains no raw
  newline, so the payload can't produce a false `READY\n` match. No protocol version bump.
- **Failure policy:** collection is one `try/except Exception`. On failure, omit the
  `ENGINE` line entirely. Identity must never block or break boot.

### Payload

```json
{
  "schema": 1,
  "manifest": { …BUILD-INFO.json verbatim, or null if absent… },
  "runtime": {
    "freecad_git": "cb497e35a3",         // FreeCAD.ConfigGet("BuildRevisionHash")[:10]
    "freecad": "27.1.0",
    "occt": "8.0.0.rc4-e72d772e70",      // Part.OCC_VERSION
    "python": "3.13.5",
    "prefix": "/Users/user/freecad-cadclaude",   // FreeCAD.getHomePath()
    "manifest_matches_binary": true      // manifest.fork.git starts with freecad_git
  },
  "worker": {
    "path": "/Users/user/dev/ElixiCAD/freecad-workspace/cadclaude_worker.py",
    "sha256": "…",                       // of the file actually executing (__file__)
    "protocol": 2
  },
  "elixifree": {
    "path": "/Users/user/dev/ElixiCAD/freecad-workspace/elixifree",
    "sha256": "…",                       // over sorted (relpath, content) of *.py
    "files": 214
  }
}
```

- Locate the manifest at `FreeCAD.getHomePath()/BUILD-INFO.json`. This was verified to
  resolve to the install prefix.
- `manifest_matches_binary: false` catches a manifest and binary from different builds,
  for example a partial install or a hand-copied `lib/`.
- `worker.sha256` and `elixifree.sha256` cover G3. A hot-patched or stale script shows up
  as a hash that doesn't match the ElixiCAD commit the hub was built from.
- The digest reuses the walk in the existing `_elixifree_signature()`, hashing file
  contents instead of taking the newest mtime. Cost is about 214 small files once at
  boot, well under 50 ms. It is computed **once** at boot. The hot-reload purge keeps its
  own cheap mtime check.

## Component 3: ElixiHub

- **`Frames.engine_info/1`**: given the startup buffer, find `ENGINE ` up to `\n` and
  `Jason.decode` it. Return `nil` on absence or error, never crash.
  `await_ready/2` returns `{:ok, protocol, engine_info}`.
- **`Worker`** stores `engine_info` in state and exposes `Worker.engine_info/1`.
  It logs one line at start:
  `FreeCAD worker ready (OS PID n, protocol 2, engine cb497e35a3 27.1.0 occt 8.0.0.rc4, worker 3f2a…, elixifree 9c1d…)`.
- **`WorkerPool.engine_info/0`** returns the identity of any live worker. All workers run
  the same binary, but each one reports its own. If two live workers disagree (a mid-swap
  restart), log a warning naming both. That warning is the cheap "engine changed" signal.
- **`Elixihub.BuildInfo.engine/0`** is a thin delegate, so engine identity sits next to
  the app version and `git_sha` that the module already owns.
- **Issue reports:** `IssueReports` already stamps `app_version` and `git_sha`
  (`issue_reports.ex:161`). Add `engine` containing `manifest.fork.git`,
  `upstream.base`, `versions`, `fork.dirty`, `worker.sha256` and `elixifree.sha256`.
  Only the summary is stamped, not the whole payload.
- **Settings UI** (`settings_live/show.ex`): a read-only "FreeCAD engine" section showing
  fork commit (linked to GitHub), upstream base, FreeCAD, OCCT, Python and Qt versions,
  SDK, build time, and a **warning badge** when `fork.dirty`, `manifest_matches_binary`
  is false, or `worker.sha256` doesn't match the hub checkout's
  `freecad-workspace/cadclaude_worker.py`. A bare-READY or ENGINE-less worker shows
  "unavailable". It lives next to the existing protocol-mismatch error label (`show.ex:378`).

## Component 4: One worker script

ElixiCAD's `freecad-workspace/cadclaude_worker.py` is the only worker.

- **Fork:** replace `src/Mod/CadClaude/cadclaude_worker.py` with a symlink into the ElixiCAD
  checkout. This mirrors the existing `src/Mod/CadClaude/elixifree` symlink, so
  `cmake --install` produces a live link and the "re-copy the worker to the mini" step
  (the `show.ex:380` error text) goes away on this machine.
- Delete the fork's `src/Mod/CadClaude/tests/test_worker_protocol.py`. Its subject moves
  to ElixiCAD's tests, beside the new `ENGINE` tests.
- **Docker/Fly:** no change is needed. `Dockerfile:114` already overwrites the file with
  ElixiCAD's copy. The fork image's dangling symlink is the same existing, known condition
  as `elixifree` (Docker CI already red for that reason, per the 2026-08 notes).
- Nothing is lost by dropping the fork's copy. A function-level comparison on 2026-11-10
  shows ElixiCAD's worker already has everything from the Sep 29 hot-patch (commit
  `55ef89c951`): `_open_protocol_stream`, `_purge_stale_elixifree`, `_metrics_line` and
  `_rusage_snapshot`. It also has more: protocol-2 framing and the Mesh and FreeCADGui
  fallbacks. The only fork-only code is `_collect_build_info` and `_ready_line`, which
  Component 2 replaces.

## Component 5: Sync process (align-upstream skill)

- **Preflight:** save the production `BUILD-INFO.json` and a production `ENGINE` line.
  For a pre-manifest install, the plan's first sync records an `ENGINE` line only.
- **Worker smoke gate:** drive the worker **as ElixiHub does**:
  `FREECAD_WORKER_PY=<ElixiCAD>/freecad-workspace/cadclaude_worker.py`, `ELIXIFREE_PATH`
  set, protocol-2 header `<len> <job_id>`, and expect `RESULT_START <job_id>`. Assert the
  `ENGINE` line's `manifest.fork.git` equals the built commit.
- **Disclosure:** replace the hand-written runtime-shift row with
  `diff <(jq -S . old/BUILD-INFO.json) <(jq -S . new/BUILD-INFO.json)`, pasted into the
  checkpoint-2 question.
- **Harness lessons** from this sync go into the skill's gotchas table:
  - `FreeCADCmd` needs `DYLD_LIBRARY_PATH=<prefix>/lib:<OCCT>/lib`, with conda as a fallback.
  - FreeCAD's exit truncates pytest's short summary, so diff the per-test `-v` lines.
  - The ElixiCAD suite needs `--ignore=<ElixiCAD>/.claude`.
- **Hard rule:** the sync merge subject must be `Merge upstream FreeCAD main <sha>`,
  because Component 1 derives `upstream.base` from it.

## Rollout order

Each step ships on its own and is backward compatible with the steps before it.

1. **Manifest** (fork). Visible immediately via `cat ~/freecad-cadclaude/BUILD-INFO.json`.
2. **`ENGINE` line** (ElixiCAD worker). Old hubs ignore it.
3. **ElixiHub parsing, logging, issue stamping and settings UI.** It degrades to
   "unavailable" against old workers.
4. **Single worker.** Do this last, once step 2's worker is the one being linked.
5. **Skill update**, after steps 1–2, because the gates depend on them.

## Testing

- **Fork:** run `gen-build-info.py` against a temp git repo for clean and dirty trees, a
  detached HEAD, a shallow clone (`upstream.base: null`) and the merge-subject lookup.
  CMake check: two consecutive no-op builds leave `BUILD-INFO.json`'s mtime unchanged.
- **Worker (ElixiCAD, plain Python):** the `ENGINE` line comes before `READY`, is a single
  line under the size cap, and is omitted when FreeCAD isn't importable. The digest changes
  when one elixifree file changes and is stable across runs.
- **Hub:** `Frames.engine_info/1` handles absence, a fragmented line across chunks and bad
  JSON. Test `await_ready` with `ENGINE` and `READY` in one chunk and in two. Check the
  pool warning when workers disagree, and the settings LiveView with info, without info,
  and with dirty or mismatch badges.
- **End to end:** the protocol-2 smoke against `~/freecad-cadclaude` shows the `ENGINE`
  line's `fork.git` equal to the install's `BUILD-INFO.json`.

## Open questions

- **Q1. Deployment history.** Should the hub persist `(engine identity hash, first_seen,
  last_seen)` rows, so "what engine ran on Nov 3?" is answerable after the fact? It's
  cheap (one upsert per worker start), but it's a new table. The proposal leaves it out
  of v1 and relies on logs plus issue-report stamps.
- **Q2. Hybrid peers.** Remote workers (the Mac mini behind the dispatcher, Fly) report
  their own identity to their own node. Should peer status carry the engine summary so the
  web node can show "mini runs engine X"? Proposed as a follow-up.
- **Q3. Fork worker symlink vs vendoring.** A symlink is consistent with `elixifree` and
  keeps prod live, but it couples the fork's install to an ElixiCAD checkout path. The
  alternative is for `freecad-worker` to *require* `FREECAD_WORKER_PY` and fail clearly
  without it. Is any launch path left that relies on the Mod-tree copy?
