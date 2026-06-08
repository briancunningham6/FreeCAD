"""
ElixiFree SIP domain module — wall panels.
All functions take plain values and return native Part.Shape.
Stock table matches sip_stock_materials.json catalog.
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

# Spline groove dimensions (mm) — matches sip_construction profile catalog
_GROOVE_WIDTH = 45
_GROOVE_DEPTH = 50

# Bottom/top plate channel dimensions (mm)
_CHANNEL_DEPTH = 90  # plate seats 90mm into the core


def _resolve_stock(stock):
    if stock not in _STOCK:
        raise ValueError(
            f"Unknown SIP stock '{stock}'. Valid values: {list(_STOCK.keys())}"
        )
    core, face = _STOCK[stock]
    return core, face, core + 2 * face


def sip_panel(width, height, stock="SIP-200"):
    """
    3-layer OSB/EPS/OSB solid.
    Axes: X = panel width, Y = total thickness (OSB+core+OSB), Z = panel height.
    """
    core, face, total = _resolve_stock(stock)
    skin1 = Part.makeBox(width, face, height, Vector(0, 0, 0))
    foam = Part.makeBox(width, core, height, Vector(0, face, 0))
    skin2 = Part.makeBox(width, face, height, Vector(0, face + core, 0))
    return skin1.fuse(foam).fuse(skin2)


def spline_groove(panel, side="left", stock="SIP-200"):
    """
    Cut a spline groove into the left or right edge of a panel.
    Groove is cut from the face (Y=face_mm) into the core only — skins stay intact.
    """
    if side not in ("left", "right"):
        raise ValueError(f"spline_groove() side must be 'left' or 'right', got '{side}'")
    core, face, total = _resolve_stock(stock)
    bb = panel.BoundBox
    height = bb.ZLength

    if side == "left":
        x = 0
    else:
        x = bb.XLength - _GROOVE_WIDTH

    groove = Part.makeBox(_GROOVE_WIDTH, _GROOVE_DEPTH, height, Vector(x, face, 0))
    return panel.cut(groove)


def route_core_channel(panel, edge="bottom", stock="SIP-200"):
    """
    Route a plate channel into the foam core at the bottom or top edge.
    Removes foam to depth _CHANNEL_DEPTH, leaving both OSB skins intact.
    The channel is full-width and runs the full panel thickness (Y axis).
    """
    if edge not in ("bottom", "top"):
        raise ValueError(
            f"route_core_channel() edge must be 'bottom' or 'top', got '{edge}'"
        )
    core, face, total = _resolve_stock(stock)
    bb = panel.BoundBox
    width = bb.XLength

    if edge == "bottom":
        z = 0
    else:
        z = bb.ZLength - _CHANNEL_DEPTH

    # Cut only the core layer: Y from face to face+core
    channel = Part.makeBox(width, core, _CHANNEL_DEPTH, Vector(0, face, z))
    return panel.cut(channel)


def panel_zone(width, height, stock="SIP-200"):
    """Alias for sip_panel — matches the 'panel zone' terminology in the SIP skill."""
    return sip_panel(width, height, stock=stock)


# Wall assembly constants (from sip_construction catalog)
_PANEL_SHEET_WIDTH = 1220   # standard SIP sheet width mm
_BOTTOM_PLATE_H = 90        # PT timber sole plate height mm
_TOP_PLATE_H = 180          # double top plate (2× 45mm) height mm
_SPLINE_WIDTH = 45          # inter-panel spline timber width mm


def sip_wall(span, panel_height, stock="SIP-200"):
    """
    Complete SIP wall assembly: sole plate + SIP panel array + inter-panel splines
    + double top plate. Returns a single fused Part.Shape ready to add to the doc.

    Axes: X = wall span, Y = total panel thickness, Z = full wall height
    (= BOTTOM_PLATE_H + panel_height + TOP_PLATE_H).

    The LLM only supplies span, panel_height, and stock. All construction rules
    (plate dimensions, spline spacing, groove routing) are encoded here.

    For walls with openings use the lower-level functions (sip_panel, spline_groove,
    route_core_channel) and raw Part calls to handle the buck geometry.
    """
    core, face, total = _resolve_stock(stock)

    import math
    n_panels = math.ceil(span / _PANEL_SHEET_WIDTH)
    # Distribute span evenly across panels (last panel takes the remainder)
    panel_widths = [_PANEL_SHEET_WIDTH] * (n_panels - 1)
    panel_widths.append(span - _PANEL_SHEET_WIDTH * (n_panels - 1))

    # 1. Sole plate — sits at Z=0, panels start at Z=_BOTTOM_PLATE_H
    sole_plate = Part.makeBox(span, core, _BOTTOM_PLATE_H, Vector(0, face, 0))

    # 2. SIP panel array — routed top and bottom, spline grooves on interior joints
    x = 0
    panel_solids = []
    for i, pw in enumerate(panel_widths):
        p = sip_panel(pw, panel_height, stock=stock)
        p = route_core_channel(p, edge="bottom", stock=stock)
        p = route_core_channel(p, edge="top", stock=stock)
        if i > 0:
            p = spline_groove(p, side="left", stock=stock)
        if i < n_panels - 1:
            p = spline_groove(p, side="right", stock=stock)
        # Translate to position: X offset, Z raised by sole plate
        copy = p.copy()
        copy.translate(Vector(x, 0, _BOTTOM_PLATE_H))
        panel_solids.append(copy)
        x += pw

    # 3. Inter-panel splines — 45mm wide, core depth, full panel height
    spline_solids = []
    x = 0
    for pw in panel_widths[:-1]:
        x += pw
        spline = Part.makeBox(
            _SPLINE_WIDTH, core, panel_height,
            Vector(x - _SPLINE_WIDTH / 2, face, _BOTTOM_PLATE_H)
        )
        spline_solids.append(spline)

    # 4. Double top plate — sits immediately above panels
    top_z = _BOTTOM_PLATE_H + panel_height
    top_plate = Part.makeBox(span, core, _TOP_PLATE_H, Vector(0, face, top_z))

    # 5. Fuse everything
    result = sole_plate
    for s in panel_solids + spline_solids:
        result = result.fuse(s)
    result = result.fuse(top_plate)
    return result.removeSplitter()
