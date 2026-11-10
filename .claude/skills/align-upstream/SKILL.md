---
name: align-upstream
description: Use when syncing this FreeCAD fork with upstream FreeCAD/FreeCAD — pulling in the latest upstream changes, resolving fork merge conflicts, or verifying that an upstream sync still builds and works with ElixiCAD (StdIO worker, elixifree suite, production install).
---

# Align Upstream

Sync the fork with upstream on an isolated branch, verify the headless build + ElixiCAD integration through hard gates, and only then merge back and swap the production install. Nothing production-facing (`main`, `feat/elixifree-core`, `build/`, `~/freecad-cadclaude`) is touched until every gate passes.

## Hard rules

- **Pin the target**: `git fetch upstream`, then merge an exact SHA of `upstream/main` — never a moving ref, and never a release branch (release lines fork earlier and may lack compat work the fork needs; upstream `main` is the target).
- **Isolation trio**: branch `sync/upstream-YYYY-MM-DD`, build dir `build-sync/`, install prefix `~/freecad-cadclaude-sync`. Never write elsewhere before the gates pass.
- **Two user checkpoints, only these**: (1) before pushing to origin, (2) before swapping the production install. Everything else runs without pausing.
- **Sync merge subject is exactly `Merge upstream FreeCAD main <sha>`** — `BUILD-INFO.json` derives `upstream.base` from it.
- **Parity, not green, is the bar**: pre-existing test failures are fine; any test that passed at baseline and fails on the sync build blocks the merge.

## Process

1. **Preflight** — tracked tree clean (commit WIP first). Save `~/freecad-cadclaude/BUILD-INFO.json` (if present) and the production `ENGINE` line (printed by `scripts/smoke_p2.py`). Capture the baseline under the *current production binary*: `scripts/run-suites.sh <bin> baseline <outdir>` (elixifree + ElixiCAD `-m freecad` suites; it handles `--continue-on-collection-errors`, `sys.path`, dyld, and env-unsetting, and writes `<label>-<suite>-v.txt` per-test lists). pytest must be available to FreeCAD's embedded Python (see "Running tests" in `src/Mod/CadClaude/elixifree/README.md`). The sync run uses the same script, changing only the binary and label.
2. **Size the conflict surface before branching**: `git merge-tree --write-tree --name-only HEAD <sha>` lists every conflicting file up front. Resolve-by-policy anything the table below covers; anything else gets read before the merge starts.
3. **Branch + merge**: `git checkout -b sync/upstream-YYYY-MM-DD feat/elixifree-core`, `git merge --no-commit --no-ff <sha>`, resolve per the policy table, verify the survival checklist, commit. Then `git submodule update --init --recursive` — upstream bumps submodule pointers and stale working dirs poison the build.
4. **Configure + build, isolated**: use the configure block in `ELIXICAD-BUILD.md` (the source of truth — update it whenever drift forces a change) with `-B build-sync`. The configure log must show OpenCASCADE resolving to `/Users/user/dev/OCCT/install` — a Homebrew/conda OCCT silently winning is a failure to fix, not ignore. Build the `Part` target first (the OCCT canary — all compat risk concentrates there), then full build, then `cmake --install build-sync --prefix ~/freecad-cadclaude-sync`.
5. **Gates — all must pass**:
   - Sanity boot: `FreeCADCmd -c "import Part; print(Part.makeBox(10,10,10).Volume)"` → `1000.0`.
   - Worker smoke: `scripts/smoke_p2.py <sync-prefix>/bin/freecad-worker --expect-git <built sha10>`. It drives ElixiCAD's worker as ElixiHub does (`FREECAD_WORKER_PY` + `ELIXIFREE_PATH`), prints the `ENGINE` line, and fails unless `runtime.freecad_git` matches.
   - elixifree and ElixiCAD parity: `scripts/run-suites.sh <sync-prefix>/MacOS/FreeCADCmd sync <outdir>`, then `diff <outdir>/baseline-<suite>-v.txt <outdir>/sync-<suite>-v.txt` for each suite — must be empty.
6. **Merge back** (checkpoint 1: ask the user): merge sync branch into `feat/elixifree-core` (`--no-ff`), then `git merge --ff-only feat/elixifree-core` onto `main` — if ff fails, stop and inspect. Before pushing, `git fetch origin && git log main..origin/main`: if origin diverged (direct PRs land there), preserve those commits via merge — never force-push.
7. **Swap** (checkpoint 2: ask the user): `mv ~/freecad-cadclaude ~/freecad-cadclaude-pre-sync-<date>` then move the sync prefix into place. Checkpoint 2's question includes the manifest diff: `diff <(jq -S . old/BUILD-INFO.json) <(jq -S . new/BUILD-INFO.json)`. After the swap, re-run `scripts/smoke_p2.py ~/freecad-cadclaude/bin/freecad-worker --expect-git <sha10>` against the production path; the `ENGINE` line proves which engine is live. Keep the rollback dir, old build dir, and sync branch ~a week.
8. **Docs**: update `ELIXICAD-BUILD.md` — sync-base line ("Fork synced to upstream `<sha>` (<date>)"), any flag/dependency drift, any new residual patches.

## Conflict policy

| Path | Resolution |
|---|---|
| `src/Mod/Part/App/**` | Prefer upstream **if** upstream absorbed what our patch addressed (e.g. OCCT compat) — read both diffs and confirm equivalence; never pattern-match a previous sync's table blindly |
| `.github/workflows/{build_release,codeql}.yml` | Keep ours — the fork intentionally disables release/schedule/push triggers |
| `cMake/FreeCAD_Helpers/SetupQt.cmake` | Upstream base, re-apply fork intent only if upstream still lacks it (`qt6_add_translation`, unconditional `LinguistTools`) |
| `src/Mod/CadClaude/**` | Fork-only code; a conflict means upstream added a colliding path — hand-inspect, no blanket strategy |
| Anything else | Hand-inspect |

**Survival checklist** (verify after merge, before building): CadClaude module + `elixifree` symlink; `TKDEGLTF` omission in `cMake/FindOCC.cmake`; `CadClaude` registered in `src/Mod/CMakeLists.txt`; `freecad-worker` install rule in root `CMakeLists.txt`; `Dockerfile`; `scripts/freecad-worker`.

## Gotchas — each one burned a real sync

| Trap | Counter |
|---|---|
| Shell exports `FREECAD_PATH`/`FREECAD_WORKER_PATH`/`FREECAD_WORKER_PY` → smoke test silently runs the OLD binary and false-passes | `env -u` all three on every evidence run; confirm the running binary via `ps` or the READY payload |
| `MIX_ENV=dev` exported → `mix test` aborts | `env -u MIX_ENV mix ...` |
| Stale submodule working dirs after merge | `git submodule update --init --recursive` before configure |
| Upstream added workbenches / renamed cmake options | New module → `-DBUILD_<X>=OFF` (headless set: Part/PartDesign/Sketcher/Material only); record every change in `ELIXICAD-BUILD.md` |
| Custom OCCT is a prerelease; upstream's version guards assume the final API | Guard residual fixes `#if OCC_VERSION_HEX >= 0x0N0000 && !defined(OCC_VERSION_DEVELOPMENT)` so they self-retire on the final release |
| `origin/main` diverged via direct PRs | Fetch + inspect before push; merge, never force |
| `FreeCADCmd` fails to load libs (its rpath is only `/usr/local/lib`) | Set `DYLD_LIBRARY_PATH=<prefix>/lib:<OCCT>/lib` as `scripts/freecad-worker` does; `run-suites.sh` already does |
| FreeCAD's exit truncates pytest's short summary, so counts/failure lines are missing from the log tail | Diff the `-v` per-test lines (`<label>-<suite>-v.txt`), never the summary |
| `ElixiCAD/.claude/worktrees` pollutes pytest collection | `--ignore=<ElixiCAD>/.claude` (built into `run-suites.sh`) |
| The fork's `freecad-worker` is not what ElixiHub runs; ElixiHub runs ElixiCAD's `cadclaude_worker.py` | Smoke with `smoke_p2.py` (sets `FREECAD_WORKER_PY`/`ELIXIFREE_PATH`); `--no-worker-env` tests the fork's own worker |
| The CommandLineTools SDK disappears (OS update) and the build fails oddly | Check `<sdk>/usr/lib/libz.tbd` exists before configuring |
| ElixiCAD `scripts/verify.sh` fails on dev checkouts for environment reasons | Distinguish env-caused from sync-caused; the `-m freecad` pytest parity diff is the real signal |
| Runtime shifts ride along invisibly (embedded Python, OCCT kernel) | Diff the old vs new `BUILD-INFO.json` (`diff <(jq -S . old) <(jq -S . new)`); disclose any interpreter/kernel change to the user explicitly |

## Rollback

Pre-merge failure: delete the sync branch, `build-sync/`, and the sync prefix — production never knew. Post-swap issue: swap the install dirs back; `git revert -m 1 <merge-commit>` on the branches.
