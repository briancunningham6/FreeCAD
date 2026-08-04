> **HISTORICAL (2026-08):** Upstream FreeCAD main now ships official OCCT 7/8
> compatibility ("Make common between OCCT 7 and 8" campaign). The patch
> strategy below was used between April–August 2026 and has been dropped in
> favor of upstream's guarded support. Kept for reference for future OCCT
> release-candidate experiments.

# FreeCAD + OpenCASCADE RC Compatibility Patch Guide

## Goal
Enable FreeCAD (main branch) to build against a newer, unreleased OpenCASCADE (OCCT) version.

This is an **engineering experiment**, not a guaranteed-compatible setup.

---

## Core Strategy

We are NOT trying to refactor FreeCAD.

We are:
- Fixing **compile-time compatibility issues**
- Making **minimal, targeted patches**
- Updating code where OCCT APIs or include behavior changed

---

## Key Problem Areas

### 1. Missing OCCT Types
Errors like:
- `TopTools_ListOfShape` unknown
- Headers not found

Cause:
- OCCT no longer exposes types via transitive includes

### 2. Removed Iterator Headers
Old headers like:
- `TopTools_ListIteratorOfListOfShape.hxx`
- `TopTools_DataMapIteratorOf...`

Cause:
- New OCCT uses nested iterator types instead

### 3. Exception API Changes
Example:
- `Standard_ConstructionError::Raise(...)` no longer valid

### 4. Custom OCCT Discovery
Symptoms:
- FreeCAD configures against system OCCT instead of your custom build
- Build output does not show your OCCT include/lib paths

Cause:
- CMake is not pointed at your custom OpenCASCADE config package

---

## Files to Patch (Priority Order)

1. `src/Mod/Part/App/FCBRepAlgoAPI_BooleanOperation.h`
2. `src/Mod/Part/App/FCBRepAlgoAPI_BooleanOperation.cpp`
3. `src/Mod/Part/App/AppPartPy.cpp`
4. `src/Mod/Part/App/modelRefine.cpp`

Then continue with the **next first compiler error** in `src/Mod/Part/App`.

---

## Patch Actions

### A. Add Explicit Includes

If a type is used directly, ensure its header is included.

Example:

```cpp
#include <TopTools_ListOfShape.hxx>
```

Do NOT rely on indirect includes.

---

### B. Replace Legacy Iterators

Old style:

```cpp
TopTools_ListIteratorOfListOfShape it(list);
for (; it.More(); it.Next()) {}
```

New style:

```cpp
for (TopTools_ListOfShape::Iterator it(list); it.More(); it.Next()) {}
```

---

### C. Fix DataMap Iterators

Replace:

```cpp
TopTools_DataMapIteratorOfXXX it(map);
```

With:

```cpp
for (MapType::Iterator it(map); it.More(); it.Next()) {}
```

Use the actual container type in the file.

---

### D. Update Exception Handling

Replace:

```cpp
Standard_ConstructionError::Raise("message");
```

With:

```cpp
throw Standard_ConstructionError("message");
```

---

## Workflow

### 0. Configure against custom OCCT

Use your OCCT install prefix and config package path.

Example (macOS, this workspace layout):

```bash
cmake -S . -B build \
	-DCMAKE_PREFIX_PATH="/Users/user/dev/OCCT/install" \
	-DOpenCASCADE_DIR="/Users/user/dev/OCCT/install/lib/cmake/opencascade" \
	-DOCCT_CMAKE_FALLBACK=OFF
```

Expected configure output should include your custom path, e.g.:
- `OpenCASCADE include directory: /Users/user/dev/OCCT/install/include/opencascade`
- `OpenCASCADE shared libraries directory: /Users/user/dev/OCCT/install/lib`

### 1. Build fast feedback target

```bash
cmake --build build --target Part --parallel --verbose 2>&1 | tee build/occt_rc_patch_part.log
```

### 2. Iterate first error only

1. Find the **first compiler error** in `build/occt_rc_patch_part.log`
2. Patch only what is needed
3. Rebuild `Part`
4. Repeat until `Part` is clean

### 3. Run full build after Part/App stabilizes

After the `Part` target is clean:

```bash
cmake --build build --parallel --verbose 2>&1 | tee build/occt_rc_patch_full.log
```

---

## Rules

- Keep patches small
- Do not redesign code
- Do not remove functionality
- Do not patch unrelated modules
- Prefer adding includes over changing logic

---

## Success Criteria

- Build progresses past `Part/App`
- Errors decrease in number
- New errors are different (not repeating same issue)

---

## Notes

This is effectively a **forward-porting exercise**:
FreeCAD is being adapted to a newer OCCT before official support.

Expect:
- A few more iterations
- Mostly header/include fixes
- Occasional small API adjustments

---

## Optional Commit Message

```
WIP: patch FreeCAD for OpenCASCADE RC compatibility
```
