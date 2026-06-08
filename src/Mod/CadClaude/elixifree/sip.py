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
