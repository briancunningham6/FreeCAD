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

    def opening(self, x, z, width, height):
        """
        Add a door or window void cut full-depth through the wall thickness.
        x, z: position from left/bottom of wall (mm)
        width, height: opening dimensions (mm)
        Returns self for chaining.
        """
        self._openings.append({"x": x, "z": z, "width": width, "height": height})
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

        return wall.removeSplitter()

    def _params(self):
        return {
            "span": self._span,
            "height": self._height,
            "stock": self._stock,
            "openings": list(self._openings),
        }
