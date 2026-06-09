# ElixiFree Changelog

All notable changes are documented here.
Format: `## [version] — YYYY-MM-DD` followed by Added / Changed / Fixed sections.

---

## [0.2.1] — 2026-06-09

### Changed
- `elixifree/sip.py` — removed duplicated symbols (`sip_wall`, `sip_roof_panel`,
  `_STOCK`, `_resolve_stock`, `_GROOVE_WIDTH`, `_GROOVE_DEPTH`, `sip_constants`).
  Shared internals are now imported from `elixifree.domains.sip`. Public API of the
  constructability layer (`sip_panel`, `spline_groove`, `route_core_channel`,
  `panel_zone`) is unchanged.
- Old flat test files in `tests/` deleted — all tests now live under `elixifree/tests/`.

### Added
- `elixifree/tests/test_sip_constructable.py` — 12 tests for the constructability layer,
  organised into `TestSipPanel`, `TestSplineGroove`, `TestRouteCoreChannel`, `TestPanelZone`.

---

## [0.2.0] — 2026-06-09

### Added
- `Wall.orient(axis)` — rotate wall output so span runs along Y instead of X (east/west walls)
- `Wall.corner_spline(side)` — add a protruding 45mm timber spline at a vertical wall edge
- `Wall.inner_groove(x, width, depth)` — cut a spline receiver groove on the inner wall face
- `sip_constants(stock)` — top-level function returning face/core/total/groove dimensions for a stock type
- `elixifree/tests/` package with `conftest.py` — shared path setup; no more `sys.path.insert` boilerplate in every test file
- `elixifree/tests/test_builder.py` — organised into `TestBuildResult`, `TestBuildError`, `TestComponentBuilder` classes
- `elixifree/tests/test_core.py` — organised into per-function test classes
- `elixifree/tests/test_domains_sip.py` — organised into per-builder test classes with full coverage of all methods
- `__all__` declarations in `__init__.py`, `domains/__init__.py`, `domains/sip.py`
- Full docstrings with Args/Returns on all public functions and builder methods
- `README.md` — architecture overview, quick start, Wall builder reference, design principles
- `CHANGELOG.md` — this file

### Fixed
- `BuildResult.add_to_doc()` now calls `FreeCAD.setActiveDocument()` after `newDocument()` in headless mode, preventing `EXPORT_ERROR: No active FreeCAD document available for export`

---

## [0.1.0] — 2026-05-28

### Added
- `elixifree` core layer: `box`, `cylinder`, `fuse`, `cut`, `translate`, `mirror`, `fillet`, `chamfer`, `add_to_doc`
- `elixifree.builder`: `BuildResult`, `BuildError`, `ComponentBuilder` base class with `build()`, `_validate()`, `_build_geometry()`, `_params()`, `_log_gap()` hooks
- `elixifree.domains.sip`: `Wall`, `RoofPanel`, `Foundation` design-stage builders
- `Wall.opening(x, z, width, height)` — cut full-thickness door/window voids
- `RoofPanel.pitch(degrees)` — pitch angle (logs gap, applies raw taper cut)
- `Foundation(length, width, depth, type)` — concrete slab; unsupported types log gap and degrade gracefully
- SIP stock table: SIP-100, SIP-150, SIP-200, SIP-250, SIP-300
- Spline groove constants: 45mm wide, 50mm deep (from SIP construction catalog)
- `elixifree.sip` constructability layer: `sip_panel`, `spline_groove`, `route_core_channel`, `panel_zone`, `sip_wall`
