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
- **Parity, not green, is the bar**: pre-existing test failures are fine; any test that passed at baseline and fails on the sync build blocks the merge.

## Process

1. **Preflight** — tracked tree clean (commit WIP first). Capture the baseline: run the elixifree suite under the *current production binary* and save the log. The suite needs `--continue-on-collection-errors`, `sys.path` insertion of `src/Mod/CadClaude`, and pytest available to FreeCAD's embedded Python (see "Running tests" in `src/Mod/CadClaude/elixifree/README.md`). Record the exact invocation — the sync run must replicate it, changing only the binary.
2. **Size the conflict surface before branching**: `git merge-tree --write-tree --name-only HEAD <sha>` lists every conflicting file up front. Resolve-by-policy anything the table below covers; anything else gets read before the merge starts.
3. **Branch + merge**: `git checkout -b sync/upstream-YYYY-MM-DD feat/elixifree-core`, `git merge --no-commit --no-ff <sha>`, resolve per the policy table, verify the survival checklist, commit. Then `git submodule update --init --recursive` — upstream bumps submodule pointers and stale working dirs poison the build.
4. **Configure + build, isolated**: use the configure block in `ELIXICAD-BUILD.md` (the source of truth — update it whenever drift forces a change) with `-B build-sync`. The configure log must show OpenCASCADE resolving to `/Users/user/dev/OCCT/install` — a Homebrew/conda OCCT silently winning is a failure to fix, not ignore. Build the `Part` target first (the OCCT canary — all compat risk concentrates there), then full build, then `cmake --install build-sync --prefix ~/freecad-cadclaude-sync`.
5. **Gates — all must pass**:
   - Sanity boot: `FreeCADCmd -c "import Part; print(Part.makeBox(10,10,10).Volume)"` → `1000.0`.
   - Worker smoke: drive `~/freecad-cadclaude-sync/bin/freecad-worker` through the protocol (`READY` → length-prefixed script → `RESULT_START/END`); the READY line's JSON payload reports the build identity — check its `git` hash matches the sync build.
   - elixifree parity: same invocation as baseline, new binary; `grep '^FAILED\|^ERROR' | sort | diff` the two logs — must be empty.
   - ElixiCAD suite: from `/Users/user/dev/ElixiCAD/elixihub`, run the `-m freecad` pytest suite under both binaries and diff failure lists the same way.
6. **Merge back** (checkpoint 1: ask the user): merge sync branch into `feat/elixifree-core` (`--no-ff`), then `git merge --ff-only feat/elixifree-core` onto `main` — if ff fails, stop and inspect. Before pushing, `git fetch origin && git log main..origin/main`: if origin diverged (direct PRs land there), preserve those commits via merge — never force-push.
7. **Swap** (checkpoint 2: ask the user): `mv ~/freecad-cadclaude ~/freecad-cadclaude-pre-sync-<date>` then move the sync prefix into place. Re-run the worker smoke against the production path; the READY build-identity hash proves which engine is live. Keep the rollback dir, old build dir, and sync branch ~a week.
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
| ElixiCAD `scripts/verify.sh` fails on dev checkouts for environment reasons | Distinguish env-caused from sync-caused; the `-m freecad` pytest parity diff is the real signal |
| Runtime shifts ride along invisibly (embedded Python, OCCT kernel) | Compare the READY build-identity payload old vs new; disclose any interpreter/kernel change to the user explicitly |

## Rollback

Pre-merge failure: delete the sync branch, `build-sync/`, and the sync prefix — production never knew. Post-swap issue: swap the install dirs back; `git revert -m 1 <merge-commit>` on the branches.
