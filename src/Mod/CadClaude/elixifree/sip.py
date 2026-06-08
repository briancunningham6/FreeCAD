# Deployed to Mod/CadClaude/elixifree/ alongside cadclaude_worker.py.
# Keep in sync with FreeCAD repo: src/Mod/CadClaude/elixifree/sip.py
"""
ElixiFree SIP domain module.

Design-stage functions (use these during component generation):
  sip_wall(span, height, stock, openings) -> Shape
  sip_roof_panel(span, depth, stock)      -> Shape

Constructability functions (used by the assembly pipeline, not component generation):
  sip_panel, spline_groove, route_core_channel, sip_constants
"""
import Part
from FreeCAD import Vector

# (core_mm, face_mm) — face is OSB thickness (11mm each side)
_STOCK = {
    "SIP-100": (100, 11),
    "SIP-150": (150, 11),
    "SIP-200": (200, 11),
    "SIP-250": (250, 11),
    "SIP-300": (300, 11),
}

# Spline groove dimensions (mm)
_GROOVE_WIDTH = 45
_GROOVE_DEPTH = 50
_CHANNEL_DEPTH = 90


def _resolve_stock(stock):
    if stock not in _STOCK:
        raise ValueError(
            f"Unknown SIP stock '{stock}'. Valid values: {list(_STOCK.keys())}"
        )
    core, face = _STOCK[stock]
    return core, face, core + 2 * face


# ── Design-stage functions ────────────────────────────────────────────────────

def sip_wall(span, height, stock="SIP-200", openings=None):
    """
    Design-intent wall: single solid block (span × thickness × height) with
    spline grooves on both vertical edges and opening voids cut through full
    thickness.

    Axes: X = span, Y = total SIP thickness, Z = height.
    The solid represents the full wall face — no panel splits, no plate routing,
    no framing. Constructability detail is added later by the assembly pipeline.

    openings: list of dicts with keys x, z, width, height (all mm, relative to
              wall local origin). Each opening is cut full-depth through Y.
              Example: [{"x": 1500, "z": 0, "width": 900, "height": 2100}]
    """
    core, face, total = _resolve_stock(stock)

    # Single solid block
    wall = Part.makeBox(span, total, height)

    # Spline grooves on both vertical edges (left and right)
    left_groove = Part.makeBox(_GROOVE_WIDTH, _GROOVE_DEPTH, height,
                               Vector(0, face, 0))
    right_groove = Part.makeBox(_GROOVE_WIDTH, _GROOVE_DEPTH, height,
                                Vector(span - _GROOVE_WIDTH, face, 0))
    wall = wall.cut(left_groove).cut(right_groove)

    # Opening voids — cut full thickness
    for o in (openings or []):
        void = Part.makeBox(o["width"], total, o["height"],
                            Vector(o["x"], 0, o["z"]))
        wall = wall.cut(void)

    return wall.removeSplitter()


def sip_roof_panel(span, depth, stock="SIP-200"):
    """
    Design-intent roof panel: single solid block (span × thickness × depth).

    Axes: X = span across slope, Y = total SIP thickness, Z = depth along slope.
    No panel splits or construction detail — that is added by the assembly pipeline.
    """
    core, face, total = _resolve_stock(stock)
    return Part.makeBox(span, total, depth)


# ── Constructability functions (assembly pipeline use only) ──────────────────

def sip_panel(width, height, stock="SIP-200"):
    """Single 3-layer OSB/EPS/OSB panel. Used by the constructable assembly pipeline."""
    core, face, total = _resolve_stock(stock)
    skin1 = Part.makeBox(width, face, height, Vector(0, 0, 0))
    foam = Part.makeBox(width, core, height, Vector(0, face, 0))
    skin2 = Part.makeBox(width, face, height, Vector(0, face + core, 0))
    return skin1.fuse(foam).fuse(skin2)


def spline_groove(panel, side="left", stock="SIP-200"):
    """Cut spline groove into panel edge. Used by the constructable assembly pipeline."""
    if side not in ("left", "right"):
        raise ValueError(f"spline_groove() side must be 'left' or 'right', got '{side}'")
    core, face, total = _resolve_stock(stock)
    bb = panel.BoundBox
    x = 0 if side == "left" else bb.XLength - _GROOVE_WIDTH
    groove = Part.makeBox(_GROOVE_WIDTH, _GROOVE_DEPTH, bb.ZLength, Vector(x, face, 0))
    return panel.cut(groove)


def route_core_channel(panel, edge="bottom", stock="SIP-200"):
    """Route plate channel into foam core. Used by the constructable assembly pipeline."""
    if edge not in ("bottom", "top"):
        raise ValueError(
            f"route_core_channel() edge must be 'bottom' or 'top', got '{edge}'"
        )
    core, face, total = _resolve_stock(stock)
    bb = panel.BoundBox
    z = 0 if edge == "bottom" else bb.ZLength - _CHANNEL_DEPTH
    channel = Part.makeBox(bb.XLength, core, _CHANNEL_DEPTH, Vector(0, face, z))
    return panel.cut(channel)


def panel_zone(width, height, stock="SIP-200"):
    """Alias for sip_panel."""
    return sip_panel(width, height, stock=stock)


def sip_constants(stock="SIP-200"):
    """Return construction constants for the given stock."""
    core, face, total = _resolve_stock(stock)
    return {
        "face": face,
        "core": core,
        "total": total,
        "groove_width": _GROOVE_WIDTH,
        "groove_depth": _GROOVE_DEPTH,
        "channel_depth": _CHANNEL_DEPTH,
    }
