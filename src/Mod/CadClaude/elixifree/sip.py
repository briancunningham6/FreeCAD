# Deployed to Mod/CadClaude/elixifree/ alongside cadclaude_worker.py.
# Keep in sync with FreeCAD repo: src/Mod/CadClaude/elixifree/sip.py
"""
ElixiFree SIP constructability layer.

Low-level geometry operations used by the constructable assembly pipeline.
These functions are NOT intended for LLM-generated component scripts — use
the design-stage builders in ``elixifree.domains.sip`` instead.

Functions:
    sip_panel(width, height, stock)         — 3-layer OSB/EPS/OSB panel solid
    spline_groove(panel, side, stock)       — cut spline groove into panel edge
    route_core_channel(panel, edge, stock)  — route plate channel into foam core
    panel_zone(width, height, stock)        — alias for sip_panel

Stock constants and shared helpers are sourced from ``elixifree.domains.sip``
to avoid duplication.
"""
import Part
from FreeCAD import Vector

from elixifree.domains.sip import _STOCK, _resolve_stock, _GROOVE_WIDTH, _GROOVE_DEPTH

_CHANNEL_DEPTH = 90


def sip_panel(width, height, stock="SIP-200"):
    """
    Build a single 3-layer OSB/EPS/OSB panel solid.

    Used by the constructable assembly pipeline to generate individual wall
    panels. For design-stage geometry use ``Wall`` from ``elixifree.domains.sip``.

    Args:
        width:  Panel width along X (mm).
        height: Panel height along Z (mm).
        stock:  SIP stock type. Default ``"SIP-200"``.

    Returns:
        Part.Shape — fused 3-layer solid (face / core / face).

    Raises:
        ValueError: If ``stock`` is not a recognised value.
    """
    core, face, total = _resolve_stock(stock)
    skin1 = Part.makeBox(width, face, height, Vector(0, 0, 0))
    foam = Part.makeBox(width, core, height, Vector(0, face, 0))
    skin2 = Part.makeBox(width, face, height, Vector(0, face + core, 0))
    return skin1.fuse(foam).fuse(skin2)


def spline_groove(panel, side="left", stock="SIP-200"):
    """
    Cut a spline groove into the left or right vertical edge of a panel.

    Args:
        panel: Part.Shape — the panel to cut.
        side:  ``"left"`` or ``"right"``.
        stock: SIP stock type (used to determine face thickness). Default ``"SIP-200"``.

    Returns:
        Part.Shape — the panel with the groove cut.

    Raises:
        ValueError: If ``side`` is not ``"left"`` or ``"right"``.
        ValueError: If ``stock`` is not a recognised value.
    """
    if side not in ("left", "right"):
        raise ValueError(f"spline_groove() side must be 'left' or 'right', got '{side}'")
    core, face, total = _resolve_stock(stock)
    bb = panel.BoundBox
    x = 0 if side == "left" else bb.XLength - _GROOVE_WIDTH
    groove = Part.makeBox(_GROOVE_WIDTH, _GROOVE_DEPTH, bb.ZLength, Vector(x, face, 0))
    return panel.cut(groove)


def route_core_channel(panel, edge="bottom", stock="SIP-200"):
    """
    Route a plate channel into the foam core at the bottom or top edge of a panel.

    Args:
        panel: Part.Shape — the panel to cut.
        edge:  ``"bottom"`` or ``"top"``.
        stock: SIP stock type (used to determine face thickness). Default ``"SIP-200"``.

    Returns:
        Part.Shape — the panel with the channel routed.

    Raises:
        ValueError: If ``edge`` is not ``"bottom"`` or ``"top"``.
        ValueError: If ``stock`` is not a recognised value.
    """
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
    """Alias for :func:`sip_panel`."""
    return sip_panel(width, height, stock=stock)
