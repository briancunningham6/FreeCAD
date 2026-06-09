# ElixiFree API Reference

This document covers every public symbol in ElixiFree. All geometry functions return
`Part.Shape` unless stated otherwise. All dimensions are in **millimetres**.

---

## Contents

- [elixifree — Core primitives](#elixifree--core-primitives)
  - [box](#box)
  - [cylinder](#cylinder)
  - [fuse](#fuse)
  - [cut](#cut)
  - [translate](#translate)
  - [mirror](#mirror)
  - [fillet](#fillet)
  - [chamfer](#chamfer)
  - [add\_to\_doc](#add_to_doc)
- [elixifree.builder — Builder infrastructure](#elixifreebuilder--builder-infrastructure)
  - [BuildResult](#buildresult)
  - [BuildError](#builderror)
  - [ComponentBuilder](#componentbuilder)
- [elixifree.domains.sip — SIP domain builders](#elixifreedomainssip--sip-domain-builders)
  - [sip\_constants](#sip_constants)
  - [Wall](#wall)
  - [RoofPanel](#roofpanel)
  - [Foundation](#foundation)

---

## `elixifree` — Core primitives

```python
from elixifree import box, cylinder, fuse, cut, translate, mirror, fillet, chamfer, add_to_doc
```

---

### `box`

```python
box(w, h, d, at=(0, 0, 0)) -> Part.Shape
```

Create an axis-aligned rectangular solid.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `w` | `float` | Width along X axis (mm). |
| `h` | `float` | Height along Y axis (mm). |
| `d` | `float` | Depth along Z axis (mm). |
| `at` | `tuple[float, float, float]` | `(x, y, z)` position of the bottom-left-front corner. Default `(0, 0, 0)`. |

**Returns** `Part.Shape` — a solid box.

**Example**

```python
from elixifree import box

# 100×60×40mm box at the origin
b = box(100, 60, 40)

# Same box shifted 50mm along X
b2 = box(100, 60, 40, at=(50, 0, 0))
```

---

### `cylinder`

```python
cylinder(r, h, at=(0, 0, 0)) -> Part.Shape
```

Create an upright cylinder aligned with the Z axis.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `r` | `float` | Radius (mm). |
| `h` | `float` | Height along Z axis (mm). |
| `at` | `tuple[float, float, float]` | `(x, y, z)` position of the centre of the bottom face. Default `(0, 0, 0)`. |

**Returns** `Part.Shape` — a solid cylinder.

**Example**

```python
from elixifree import cylinder

post = cylinder(r=25, h=200)
```

---

### `fuse`

```python
fuse(*shapes) -> Part.Shape
```

Compute the Boolean union of two or more shapes.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `*shapes` | `Part.Shape` | Two or more shapes to join. |

**Returns** `Part.Shape` — the unified solid.

**Raises**

- `ValueError` — if fewer than two shapes are provided.

**Example**

```python
from elixifree import box, fuse

base = box(200, 200, 20)
pillar = box(40, 40, 100, at=(80, 80, 20))
result = fuse(base, pillar)
```

---

### `cut`

```python
cut(base, *tools) -> Part.Shape
```

Subtract one or more tool shapes from a base shape. Tools are applied left to right.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `base` | `Part.Shape` | The shape to cut from. |
| `*tools` | `Part.Shape` | One or more shapes to subtract. |

**Returns** `Part.Shape` — the base with all tools removed.

**Example**

```python
from elixifree import box, cylinder, cut

outer = box(100, 100, 100)
hole = cylinder(r=20, h=100, at=(50, 50, 0))
result = cut(outer, hole)
```

---

### `translate`

```python
translate(shape, x=0, y=0, z=0) -> Part.Shape
```

Return a translated **copy** of a shape. The original shape is not modified.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The shape to move. |
| `x` | `float` | Displacement along X (mm). Default `0`. |
| `y` | `float` | Displacement along Y (mm). Default `0`. |
| `z` | `float` | Displacement along Z (mm). Default `0`. |

**Returns** `Part.Shape` — a new copy at the displaced position.

**Notes**

`translate` always returns a new object. The input shape is never mutated. This differs from
`Part.Shape.translate()` which mutates in place.

**Example**

```python
from elixifree import box, translate

shelf = box(600, 300, 18)
shelf_upper = translate(shelf, z=400)   # shelf raised 400mm
```

---

### `mirror`

```python
mirror(shape, plane="XZ") -> Part.Shape
```

Mirror a shape about a named global plane through the world origin.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The shape to mirror. |
| `plane` | `str` | Plane of reflection. One of `"XY"`, `"XZ"` (default), `"YZ"`. |

**Returns** `Part.Shape` — the mirrored copy.

**Raises**

- `ValueError` — if `plane` is not one of the three supported values.

**Notes**

The mirror plane always passes through the world origin `(0, 0, 0)`. To mirror about an
offset plane, translate the shape to centre it on the origin, mirror, then translate back.

**Example**

```python
from elixifree import box, fuse, translate, mirror

# L-bracket: build one arm, mirror it
arm = box(100, 20, 60)
mirrored = mirror(translate(arm, y=20), plane="XZ")
bracket = fuse(arm, mirrored)
```

---

### `fillet`

```python
fillet(shape, radius, edge_selector=None) -> Part.Shape
```

Round the edges of a shape.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The shape to fillet. |
| `radius` | `float` | Fillet radius (mm). |
| `edge_selector` | `callable` or `None` | Optional `(edge) -> bool` predicate. When provided, only edges for which the predicate returns `True` are filleted. When `None`, all edges are filleted. |

**Returns** `Part.Shape` — the filleted shape, or `shape` unmodified if the fillet
operation fails (OCCT frequently fails on very small radii, very large radii, or
degenerate geometry — failures are silently swallowed and logged at `DEBUG` level).

**Example**

```python
from elixifree import box, fillet

block = box(50, 50, 50)
rounded = fillet(block, radius=5)
```

---

### `chamfer`

```python
chamfer(shape, size, edge_selector=None) -> Part.Shape
```

Chamfer (bevel) the edges of a shape.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The shape to chamfer. |
| `size` | `float` | Chamfer size (mm). |
| `edge_selector` | `callable` or `None` | Optional `(edge) -> bool` predicate. Same semantics as `fillet`. |

**Returns** `Part.Shape` — the chamfered shape, or `shape` unmodified on failure.

**Example**

```python
from elixifree import box, chamfer

block = box(50, 50, 50)
bevelled = chamfer(block, size=3)
```

---

### `add_to_doc`

```python
add_to_doc(shape, name, doc=None) -> Part::Feature
```

Add a shape to a FreeCAD document as a `Part::Feature`, then recompute the document.

Creates a new document if no active document exists and `doc` is not supplied. In
headless (worker) mode the new document is also registered as the active document so
the worker can export it after script execution.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The geometry to add. |
| `name` | `str` | Name for the feature object. Also used as the document name when a new document is created. |
| `doc` | `FreeCAD.Document` or `None` | Document to add to. When `None`, uses `FreeCAD.ActiveDocument` or creates a new one. |

**Returns** `Part::Feature` — the newly created FreeCAD feature object.

**Notes**

Always call `add_to_doc` as the last statement in a component script. Do not call
`doc.recompute()` or `FreeCAD.Gui` methods manually — `add_to_doc` handles both.

**Example**

```python
from elixifree import box, cut, add_to_doc

outer = box(500, 300, 200)
inner = box(490, 290, 200, at=(5, 5, 5))
result = cut(outer, inner)
add_to_doc(result, "Body")
```

---

## `elixifree.builder` — Builder infrastructure

```python
from elixifree.builder import BuildResult, BuildError, ComponentBuilder
```

These classes are also re-exported from `elixifree`:

```python
from elixifree import BuildResult, BuildError, ComponentBuilder
```

---

### `BuildResult`

```python
class BuildResult:
    shape: Part.Shape
    params: dict
    gaps: list[str]
```

The return value of every builder's `.build()` call. Immutable after construction.

**Attributes**

| Name | Type | Description |
|------|------|-------------|
| `shape` | `Part.Shape` | The generated geometry. Assign to `feature.Shape` or pass to `add_to_doc`. |
| `params` | `dict` | Plain dict of the builder's input parameters. JSON-serialisable, diffable, usable as test fixtures. |
| `gaps` | `list[str]` | Descriptions of geometry the builder could not handle declaratively. Empty for fully-supported builds. Each entry is a short string starting with the gap name, e.g. `"pitch: pitched panels not yet supported"`. |

**Methods**

#### `add_to_doc`

```python
BuildResult.add_to_doc(name, doc=None) -> Part::Feature
```

Convenience wrapper — equivalent to `add_to_doc(self.shape, name, doc)`. See
[`add_to_doc`](#add_to_doc) for full documentation.

**Example**

```python
from elixifree.domains.sip import Wall

result = Wall(span=4000, height=2440, stock="SIP-100").build()

# Access shape directly
print(result.shape.Volume)

# Inspect parameters
print(result.params)
# {'span': 4000, 'height': 2440, 'stock': 'SIP-100', 'openings': [], ...}

# Check for gaps
if result.gaps:
    print("Library gaps:", result.gaps)

# Add to document
result.add_to_doc("Body")
```

---

### `BuildError`

```python
class BuildError(Exception)
```

Raised when builder parameters are invalid or geometry cannot be constructed.

Catching `BuildError` is the correct way to handle invalid inputs. All other exceptions
from a builder indicate unexpected failures and should propagate.

**Example**

```python
from elixifree.builder import BuildError
from elixifree.domains.sip import Wall

try:
    result = Wall(span=0, height=2440).build()
except BuildError as e:
    print(f"Invalid parameters: {e}")
```

---

### `ComponentBuilder`

```python
class ComponentBuilder(ABC)
```

Abstract base class for all ElixiFree domain builders. Subclass this to add a new
component type to any domain.

**Required methods**

Subclasses must implement all three methods. Raising `NotImplementedError` will cause
`.build()` to fail with a clear message.

#### `_validate`

```python
def _validate(self) -> None
```

Validate input parameters. Raise `BuildError` for any invalid combination. Called
before `_build_geometry`. Do not perform any geometry operations here.

#### `_build_geometry`

```python
def _build_geometry(self) -> Part.Shape
```

Build and return the geometry as a `Part.Shape`. May call `self._log_gap(description)`
for any geometry that falls back to raw Part calls.

#### `_params`

```python
def _params(self) -> dict
```

Return a plain, JSON-serialisable dict of the builder's input parameters. This dict
becomes `BuildResult.params`.

**Helper methods**

#### `_log_gap`

```python
def _log_gap(self, description: str) -> None
```

Record a geometry gap — call this when falling back to raw `Part` API for geometry the
library cannot yet express declaratively. The description is appended to
`BuildResult.gaps` and logged at `INFO` level.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Short description starting with a feature name, e.g. `"tapered_top: non-rectangular wall tops not supported"`. |

**Example — minimal builder**

```python
from elixifree.builder import ComponentBuilder, BuildError
import Part
from FreeCAD import Vector

class Wedge(ComponentBuilder):
    def __init__(self, length, height, tip_offset):
        super().__init__()
        self._length = length
        self._height = height
        self._tip_offset = tip_offset

    def _validate(self):
        if self._length <= 0:
            raise BuildError(f"length must be positive, got {self._length}")
        if self._height <= 0:
            raise BuildError(f"height must be positive, got {self._height}")

    def _build_geometry(self):
        pts = [
            Vector(0, 0, 0),
            Vector(self._length, 0, 0),
            Vector(self._tip_offset, 0, self._height),
            Vector(0, 0, 0),
        ]
        face = Part.Face(Part.makePolygon(pts))
        return face.extrude(Vector(0, 100, 0))

    def _params(self):
        return {
            "length": self._length,
            "height": self._height,
            "tip_offset": self._tip_offset,
        }
```

---

## `elixifree.domains.sip` — SIP domain builders

```python
from elixifree.domains.sip import Wall, RoofPanel, Foundation, sip_constants
```

Design-intent builders for Structural Insulated Panel (SIP) construction. Each builder
produces a single solid body representing the design geometry. Panel splits, sole plates,
splines, and structural framing are added by the constructability layer — not here.

**Coordinate convention (all builders)**

| Axis | Direction |
|------|-----------|
| X | Span / length |
| Y | Total SIP thickness |
| Z | Height / depth |

---

### `sip_constants`

```python
sip_constants(stock="SIP-200") -> dict
```

Return construction constants for the given SIP stock type.

Use this instead of hardcoding thickness values in scripts.

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `stock` | `str` | Stock identifier. One of `"SIP-100"`, `"SIP-150"`, `"SIP-200"` (default), `"SIP-250"`, `"SIP-300"`. |

**Returns** `dict` with the following keys:

| Key | Type | Description |
|-----|------|-------------|
| `"face"` | `int` | OSB face thickness (mm). Always `11`. |
| `"core"` | `int` | EPS core thickness (mm). |
| `"total"` | `int` | Total panel thickness = `face × 2 + core` (mm). |
| `"groove_width"` | `int` | Standard spline groove width (mm). Always `45`. |
| `"groove_depth"` | `int` | Standard spline groove depth into core (mm). Always `50`. |

**Raises**

- `BuildError` — if `stock` is not a recognised value.

**Stock reference**

| Stock | Face | Core | Total |
|-------|------|------|-------|
| SIP-100 | 11mm | 100mm | 122mm |
| SIP-150 | 11mm | 150mm | 172mm |
| SIP-200 | 11mm | 200mm | 222mm |
| SIP-250 | 11mm | 250mm | 272mm |
| SIP-300 | 11mm | 300mm | 322mm |

**Example**

```python
from elixifree.domains.sip import sip_constants

c = sip_constants("SIP-100")
print(c["total"])        # 122
print(c["groove_width"]) # 45
```

---

### `Wall`

```python
class Wall(ComponentBuilder)
```

Design-intent SIP wall panel. Produces a single solid with spline grooves cut on both
vertical edges. Opening voids and corner splines are added via method chaining before
calling `.build()`.

**Default axes:** X = span, Y = total thickness, Z = height. Use `.orient("Y")` to
produce X = thickness, Y = span.

#### `__init__`

```python
Wall(span, height, stock="SIP-200")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `span` | `float` | Wall length (mm). |
| `height` | `float` | Wall height (mm). |
| `stock` | `str` | SIP stock type. Default `"SIP-200"`. See [sip_constants](#sip_constants) for valid values. |

**Raises** `BuildError` on `.build()` if `span <= 0`, `height <= 0`, or `stock` is unrecognised.

#### `.opening`

```python
Wall.opening(x, z, width, height) -> Wall
```

Cut a full-thickness door or window void through the wall.

| Parameter | Type | Description |
|-----------|------|-------------|
| `x` | `float` | Distance from the left edge of the wall to the left edge of the opening (mm). |
| `z` | `float` | Distance from the wall base to the bottom of the opening (mm). Use `0` for doors. |
| `width` | `float` | Opening width (mm). |
| `height` | `float` | Opening height (mm). |

**Returns** `self` — for method chaining.

**Raises** `BuildError` on `.build()` if the opening extends beyond the wall span or height.

#### `.orient`

```python
Wall.orient(axis="Y") -> Wall
```

Rotate the output geometry so the span runs along a different world axis.

| Parameter | Type | Description |
|-----------|------|-------------|
| `axis` | `str` | `"X"` (default — span along X) or `"Y"` (span along Y). Use `"Y"` for east/west walls. |

**Returns** `self` — for method chaining.

**Raises** `BuildError` on `.build()` if `axis` is not `"X"` or `"Y"`.

#### `.corner_spline`

```python
Wall.corner_spline(side="left") -> Wall
```

Add a protruding 45mm timber spline on a vertical edge of the wall. The spline sits
in the core layer and extends past the OSB face so an adjacent perpendicular wall
can slot over it.

| Parameter | Type | Description |
|-----------|------|-------------|
| `side` | `str` | `"left"` (X=0 edge) or `"right"` (X=span edge). |

**Returns** `self` — for method chaining.

**Raises** `BuildError` on `.build()` if `side` is not `"left"` or `"right"`.

#### `.inner_groove`

```python
Wall.inner_groove(x, width=45, depth=50) -> Wall
```

Cut a vertical groove into the inner face (Y=0) of the wall to receive a spline from
a perpendicular intersecting wall.

| Parameter | Type | Description |
|-----------|------|-------------|
| `x` | `float` | Distance from the left edge of the wall to the **centre** of the groove (mm). |
| `width` | `float` | Groove width (mm). Default `45` — matches standard spline timber. |
| `depth` | `float` | Groove depth into the core (mm). Default `50`. |

**Returns** `self` — for method chaining.

#### `.build`

```python
Wall.build() -> BuildResult
```

Validate all parameters, construct the geometry, and return a `BuildResult`.

`BuildResult.params` keys:

| Key | Type | Description |
|-----|------|-------------|
| `"span"` | `float` | As provided. |
| `"height"` | `float` | As provided. |
| `"stock"` | `str` | As provided. |
| `"orientation"` | `str` | `"X"` or `"Y"`. |
| `"openings"` | `list[dict]` | List of `{"x", "z", "width", "height"}` dicts. |
| `"corner_splines"` | `list[str]` | List of `"left"` / `"right"` entries. |
| `"inner_grooves"` | `list[dict]` | List of `{"x", "width", "depth"}` dicts. |

**Example**

```python
from elixifree.domains.sip import Wall, sip_constants

c = sip_constants("SIP-100")

# North wall: full-width, grooves to receive east/west splines
result = (Wall(span=4000, height=2440, stock="SIP-100")
    .inner_groove(x=c["total"] / 2)
    .inner_groove(x=4000 - c["total"] / 2)
    .build())
result.add_to_doc("Body")

# East wall: Y-oriented, corner splines, window opening
result = (Wall(span=3000, height=2440, stock="SIP-100")
    .orient("Y")
    .corner_spline(side="left")
    .corner_spline(side="right")
    .opening(x=1050, z=900, width=900, height=1000)
    .build())
result.add_to_doc("Body")
```

---

### `RoofPanel`

```python
class RoofPanel(ComponentBuilder)
```

Design-intent SIP roof panel. Produces a flat horizontal solid.

**Axes:** X = span across slope, Y = total SIP thickness, Z = depth along slope.

#### `__init__`

```python
RoofPanel(span, depth, stock="SIP-200")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `span` | `float` | Panel width across the slope (mm). |
| `depth` | `float` | Panel depth along the slope (mm). |
| `stock` | `str` | SIP stock type. Default `"SIP-200"`. |

**Raises** `BuildError` on `.build()` if `span <= 0`, `depth <= 0`, or `stock` is unrecognised.

#### `.pitch`

```python
RoofPanel.pitch(degrees) -> RoofPanel
```

Set the roof pitch angle. **Currently a gap** — logs `BuildResult.gaps` and applies a raw
taper cut. A declarative pitched roof implementation is planned.

| Parameter | Type | Description |
|-----------|------|-------------|
| `degrees` | `float` | Pitch angle in degrees from horizontal. |

**Returns** `self` — for method chaining.

#### `.build`

```python
RoofPanel.build() -> BuildResult
```

`BuildResult.params` keys: `"span"`, `"depth"`, `"stock"`, `"pitch_degrees"` (only present if `.pitch()` was called).

**Example**

```python
from elixifree.domains.sip import RoofPanel

result = RoofPanel(span=4200, depth=3600, stock="SIP-150").build()
result.add_to_doc("Body")
```

---

### `Foundation`

```python
class Foundation(ComponentBuilder)
```

Design-intent concrete slab foundation. Produces an axis-aligned solid box.

**Axes:** X = length, Y = width, Z = depth (slab thickness).

#### `__init__`

```python
Foundation(length, width, depth, type="concrete_slab")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `length` | `float` | Foundation length along X (mm). |
| `width` | `float` | Foundation width along Y (mm). |
| `depth` | `float` | Slab thickness along Z (mm). |
| `type` | `str` | Foundation type. Currently only `"concrete_slab"` is fully supported. Unsupported types produce geometry with a gap logged — they do not raise. |

**Raises** `BuildError` on `.build()` if `length`, `width`, or `depth` is `<= 0`.

#### `.build`

```python
Foundation.build() -> BuildResult
```

`BuildResult.params` keys: `"length"`, `"width"`, `"depth"`, `"type"`.

**Example**

```python
from elixifree.domains.sip import Foundation

result = Foundation(length=4200, width=3400, depth=150).build()
result.add_to_doc("Body")
```

---

## Writing a new domain builder

To add a new component type:

1. Create `elixifree/domains/<domain>.py`
2. Subclass `ComponentBuilder`
3. Implement `_validate()`, `_build_geometry()`, `_params()`
4. Call `self._log_gap(description)` for any geometry that falls back to raw `Part` calls
5. Add tests in `elixifree/tests/test_domains_<domain>.py`
6. Export from `elixifree/domains/__init__.py`

See [elixifree/domains/sip.py](domains/sip.py) for a complete reference implementation.
