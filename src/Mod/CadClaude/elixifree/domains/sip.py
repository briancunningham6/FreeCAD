"""
ElixiFree SIP domain builders.

Design-stage builders (use these in component generation scripts):
  Wall(span, height, stock)          — plain wall or wall with openings
  RoofPanel(span, depth, stock)      — flat or pitched roof panel
  Foundation(length, width, depth)   — concrete slab foundation

Each builder returns a BuildResult with .shape (Part.Shape), .params (dict),
and .gaps (list of strings for library gaps encountered).

Usage:
  from elixifree.domains.sip import Wall

  result = (Wall(span=4000, height=2440, stock="SIP-100")
      .opening(x=1500, z=0, width=900, height=2100)
      .build())
  result.add_to_doc("Body")
"""
import Part
from FreeCAD import Vector

from elixifree.builder import ComponentBuilder, BuildError

# Stock table: name -> (core_mm, face_mm)
_STOCK = {
    "SIP-100": (100, 11),
    "SIP-150": (150, 11),
    "SIP-200": (200, 11),
    "SIP-250": (250, 11),
    "SIP-300": (300, 11),
}

# Spline groove dimensions — from sip_construction profile catalog
_GROOVE_WIDTH = 45
_GROOVE_DEPTH = 50


def _resolve_stock(stock):
    if stock not in _STOCK:
        raise BuildError(
            f"Unknown SIP stock '{stock}'. Valid values: {list(_STOCK.keys())}"
        )
    core, face = _STOCK[stock]
    return core, face, core + 2 * face


def sip_constants(stock="SIP-200"):
    """
    Return a dict of construction constants for the given stock.
    Use this instead of hardcoding CORE_THICKNESS, FACE_THICKNESS etc.

    Keys: face, core, total, groove_width, groove_depth
    Example:
        from elixifree.domains.sip import sip_constants
        c = sip_constants("SIP-100")
        # c["face"]=11, c["core"]=100, c["total"]=122
    """
    core, face, total = _resolve_stock(stock)
    return {
        "face": face,
        "core": core,
        "total": total,
        "groove_width": _GROOVE_WIDTH,
        "groove_depth": _GROOVE_DEPTH,
    }


class Wall(ComponentBuilder):
    """
    Design-intent SIP wall: single solid (span x thickness x height) with
    spline grooves on both vertical edges. Opening voids cut full-thickness.

    Axes: X = span, Y = total SIP thickness, Z = height.
    No panel splits, plates, or framing — that is the assembly pipeline's job.
    """

    def __init__(self, span, height, stock="SIP-200"):
        super().__init__()
        self._span = span
        self._height = height
        self._stock = stock
        self._openings = []
        self._corner_splines = []

    def opening(self, x, z, width, height):
        """
        Add a door or window void cut full-depth through the wall thickness.
        x, z: position from left/bottom of wall (mm)
        width, height: opening dimensions (mm)
        Returns self for chaining.
        """
        self._openings.append({"x": x, "z": z, "width": width, "height": height})
        return self

    def corner_spline(self, side="left"):
        """
        Add a protruding timber spline on a vertical edge of the wall.
        The spline sits in the core layer and extends past the OSB faces so the
        adjacent perpendicular wall can slot in.

        side: "left" (X=0 end) or "right" (X=span end)
        Returns self for chaining.

        Use this instead of raw Part.makeBox when the wall needs to receive
        a perpendicular wall at its edge. Adds 45mm of spline protrusion.
        """
        if side not in ("left", "right"):
            raise BuildError(f"corner_spline() side must be 'left' or 'right', got '{side}'")
        self._corner_splines.append(side)
        return self

    def _validate(self):
        if self._span <= 0:
            raise BuildError(f"Wall span must be positive, got {self._span}")
        if self._height <= 0:
            raise BuildError(f"Wall height must be positive, got {self._height}")
        _resolve_stock(self._stock)  # raises BuildError for unknown stock
        for i, o in enumerate(self._openings):
            if o["x"] < 0 or o["x"] + o["width"] > self._span:
                raise BuildError(
                    f"Opening {i} x-extent [{o['x']}, {o['x'] + o['width']}] "
                    f"exceeds wall span {self._span}"
                )
            if o["z"] < 0 or o["z"] + o["height"] > self._height:
                raise BuildError(
                    f"Opening {i} z-extent [{o['z']}, {o['z'] + o['height']}] "
                    f"exceeds wall height {self._height}"
                )

    def _build_geometry(self):
        core, face, total = _resolve_stock(self._stock)

        # Single solid block
        wall = Part.makeBox(self._span, total, self._height)

        # Spline grooves on both vertical edges
        left_groove = Part.makeBox(
            _GROOVE_WIDTH, _GROOVE_DEPTH, self._height,
            Vector(0, face, 0)
        )
        right_groove = Part.makeBox(
            _GROOVE_WIDTH, _GROOVE_DEPTH, self._height,
            Vector(self._span - _GROOVE_WIDTH, face, 0)
        )
        wall = wall.cut(left_groove).cut(right_groove)

        # Opening voids — cut full thickness
        for o in self._openings:
            void = Part.makeBox(o["width"], total, o["height"],
                                Vector(o["x"], 0, o["z"]))
            wall = wall.cut(void)

        # Corner splines — protruding timber in core layer at wall edges.
        # Fused before removeSplitter so OCCT resolves all faces in one pass.
        for side in self._corner_splines:
            x = -_GROOVE_WIDTH if side == "left" else self._span
            spline = Part.makeBox(_GROOVE_WIDTH, core, self._height,
                                  Vector(x, face, 0))
            wall = wall.fuse(spline)

        return wall.removeSplitter()

    def _params(self):
        return {
            "span": self._span,
            "height": self._height,
            "stock": self._stock,
            "openings": list(self._openings),
            "corner_splines": list(self._corner_splines),
        }


class RoofPanel(ComponentBuilder):
    """
    Design-intent SIP roof panel: single solid (span x thickness x depth).

    Axes: X = span across slope, Y = total SIP thickness, Z = depth along slope.
    No panel splits or construction detail — that is the assembly pipeline's job.

    .pitch(degrees) — logs a gap (pitched geometry not yet in library) and applies
    a raw taper cut. This makes the gap visible for future development.
    """

    def __init__(self, span, depth, stock="SIP-200"):
        super().__init__()
        self._span = span
        self._depth = depth
        self._stock = stock
        self._pitch_degrees = None

    def pitch(self, degrees):
        """Set roof pitch. Currently logs a gap and applies a raw taper cut."""
        self._pitch_degrees = degrees
        return self

    def _validate(self):
        if self._span <= 0:
            raise BuildError(f"RoofPanel span must be positive, got {self._span}")
        if self._depth <= 0:
            raise BuildError(f"RoofPanel depth must be positive, got {self._depth}")
        _resolve_stock(self._stock)

    def _build_geometry(self):
        import math
        core, face, total = _resolve_stock(self._stock)
        panel = Part.makeBox(self._span, total, self._depth)

        if self._pitch_degrees is not None:
            self._log_gap(
                f"pitch: pitched roof panels (pitch={self._pitch_degrees}deg) not yet "
                f"supported declaratively — using raw taper cut"
            )
            fall = self._depth * math.tan(math.radians(self._pitch_degrees))
            if fall > 0.5:
                taper_pts = [
                    Vector(0, 0, total),
                    Vector(0, 0, total + fall + 10),
                    Vector(0, self._depth, total + 10),
                    Vector(0, self._depth, total),
                    Vector(0, 0, total),
                ]
                wire = Part.makePolygon(taper_pts)
                face_shape = Part.Face(wire)
                taper_cut = face_shape.extrude(Vector(self._span, 0, 0))
                panel = panel.cut(taper_cut)

        return panel

    def _params(self):
        p = {"span": self._span, "depth": self._depth, "stock": self._stock}
        if self._pitch_degrees is not None:
            p["pitch_degrees"] = self._pitch_degrees
        return p


class Foundation(ComponentBuilder):
    """
    Design-intent SIP foundation: concrete slab solid (length x width x depth).

    Axes: X = length, Y = width, Z = depth (thickness of slab).
    type: "concrete_slab" (default) — only type currently supported.
    """

    _SUPPORTED_TYPES = ("concrete_slab",)

    def __init__(self, length, width, depth, type="concrete_slab"):
        super().__init__()
        self._length = length
        self._width = width
        self._depth = depth
        self._type = type

    def _validate(self):
        if self._length <= 0:
            raise BuildError(f"Foundation length must be positive, got {self._length}")
        if self._width <= 0:
            raise BuildError(f"Foundation width must be positive, got {self._width}")
        if self._depth <= 0:
            raise BuildError(f"Foundation depth must be positive, got {self._depth}")
        if self._type not in self._SUPPORTED_TYPES:
            self._log_gap(
                f"foundation_type: '{self._type}' not supported — "
                f"falling back to concrete_slab geometry"
            )

    def _build_geometry(self):
        return Part.makeBox(self._length, self._width, self._depth)

    def _params(self):
        return {
            "length": self._length,
            "width": self._width,
            "depth": self._depth,
            "type": self._type,
        }
