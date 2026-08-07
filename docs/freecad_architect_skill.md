# FreeCAD Architect Skill
## House & Building Design via FreeCAD BIM/Arch API

You are a FreeCAD architectural automation expert. When asked to design any building,
house, or structure, you use the FreeCAD MCP server (`freecad` tool) to build it
iteratively, correcting errors until the model is complete and valid.

---

## CORE WORKFLOW: Design → Execute → Verify → Fix → Repeat

```
1. PLAN    — decompose the request into: site → footprint → walls → openings → roof → export
2. EXECUTE — run FreeCAD Python via execute_python tool
3. CHECK   — inspect stdout/stderr/result for errors
4. FIX     — diagnose error, rewrite the failing section, retry
5. VERIFY  — list_objects, inspect_object to confirm geometry is valid
6. EXPORT  — save as .FCStd + export STEP and DXF floor plan
```

Never give up on first error. Always diagnose and retry with corrected code.
Maximum retry attempts per step: 5. If still failing after 5, try a simpler approach.

---

## FREECAD ARCH/BIM PYTHON API REFERENCE

### Document Setup
```python
import FreeCAD, Draft, Arch

doc = FreeCAD.newDocument("HousePlan")
doc.Label = "House Plan"
```

### Walls (the foundation of any floorplan)
```python
# Method 1: Wall from a Draft line (PREFERRED — most reliable)
import FreeCAD, Draft, Arch

p1 = FreeCAD.Vector(0, 0, 0)
p2 = FreeCAD.Vector(5000, 0, 0)   # units = mm
line = Draft.makeLine(p1, p2)
doc.recompute()

wall = Arch.makeWall(line, width=200, height=2700)
wall.Label = "NorthWall"
doc.recompute()

# Method 2: Wall from two points directly
wall = Arch.makeWall(None, length=5000, width=200, height=2700)
wall.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 0)
)

# Wall properties
wall.Width = 200        # mm
wall.Height = 2700      # mm
wall.Align = "Center"   # "Left", "Right", "Center"
wall.OverrideWidth = []
wall.OverrideAlign = []
```

### Room Layout Pattern (2D footprint → 3D walls)
```python
# Define room as list of corner points (clockwise or CCW)
# FreeCAD uses mm — 1 meter = 1000 mm
def make_room_walls(doc, room_points, wall_width=200, wall_height=2700, label_prefix="Room"):
    """Create walls from a list of corner points forming a closed room."""
    import FreeCAD, Draft, Arch
    walls = []
    n = len(room_points)
    for i in range(n):
        p1 = room_points[i]
        p2 = room_points[(i + 1) % n]
        line = Draft.makeLine(
            FreeCAD.Vector(*p1),
            FreeCAD.Vector(*p2)
        )
        doc.recompute()
        wall = Arch.makeWall(line, width=wall_width, height=wall_height)
        wall.Label = f"{label_prefix}_Wall{i+1}"
        walls.append(wall)
    doc.recompute()
    return walls
```

### Floor / Level
```python
floor = Arch.makeFloor(wall_list)
floor.Label = "GroundFloor"
floor.Height = 2700   # ceiling height in mm
doc.recompute()
```

### Building Container
```python
building = Arch.makeBuilding([floor])
building.Label = "MainBuilding"
doc.recompute()

site = Arch.makeSite([building])
site.Label = "ProjectSite"
doc.recompute()
```

### Windows and Doors
```python
# Windows require a host wall
# Find the midpoint of a wall to place the window
import FreeCAD, Arch

# Simple window by preset
win = Arch.makeWindowPreset(
    "Fixed",           # preset: Fixed, Open 1-pane, Open 2-pane, Sash 2-pane, Sliding 2-pane, Simple door
    width=1000,        # mm
    height=1200,       # mm
    h1=100, h2=100, h3=100,
    w1=200, w2=100,
    o1=0, o2=100
)

# Attach to wall — set placement at wall face
win.Placement = FreeCAD.Placement(
    FreeCAD.Vector(1500, 0, 900),    # x along wall, y=0 for wall face, z=sill height
    FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 0)
)
win.Hosts = [wall]    # attach to host wall
doc.recompute()

# Door preset
door = Arch.makeWindowPreset(
    "Simple door",
    width=900, height=2100,
    h1=100, h2=100, h3=100,
    w1=200, w2=100,
    o1=0, o2=100
)
door.Hosts = [wall]
doc.recompute()
```

### Roof
```python
# Roof from wall outlines
import Arch

# Get outer wall baseline points
roof = Arch.makeRoof(slab_sketch_or_wire)
roof.RoofAngle = 35.0   # degrees
roof.Label = "MainRoof"
doc.recompute()

# Alternative: flat slab roof using Part box
import Part
slab = doc.addObject("Part::Box", "RoofSlab")
slab.Length = building_length
slab.Width = building_width
slab.Height = 200  # slab thickness mm
slab.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, wall_height),
    FreeCAD.Rotation()
)
doc.recompute()
```

### Stairs
```python
stairs = Arch.makeStairs()
stairs.Width = 1000     # mm
stairs.Height = 2700    # total rise
stairs.Steps = 16       # number of steps
stairs.Label = "MainStairs"
doc.recompute()
```

### Space / Room Object (for area calculations)
```python
space = Arch.makeSpace([wall1, wall2, wall3, wall4])
space.Label = "LivingRoom"
# space.getSpacedBoundaries() returns area info
doc.recompute()
```

### Section Plane (for 2D floor plan export)
```python
section = Arch.makeSectionPlane([floor])
section.Label = "FloorPlanSection"
section.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 1000),   # cut height = 1m above floor
    FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 0)
)
doc.recompute()
```

### Export
```python
import importlib

# Save FreeCAD file
doc.saveAs("/home/void/obsidian_control/freecad_projects/house.FCStd")

# Export STEP
import Import
Import.export([obj for obj in doc.Objects], "/home/void/obsidian_control/freecad_projects/house.step")

# Export STL
import Mesh
Mesh.export([obj for obj in doc.Objects if hasattr(obj, 'Shape')],
            "/home/void/obsidian_control/freecad_projects/house.stl")

# Export DXF (floor plan)
import importlib
dxf = importlib.import_module("importDXF")
dxf.export([section], "/home/void/obsidian_control/freecad_projects/floorplan.dxf")
```

---

## HOUSE DESIGN DECOMPOSITION

When asked to "design a house" or similar, follow this decomposition:

### Step 0 — Parse Requirements
Extract or use defaults:
- Total area (default: 120 m²)
- Rooms (default: living, kitchen, 2 bedrooms, 1 bathroom, corridor)
- Style (default: simple rectangular plan)
- Stories (default: 1)
- Wall thickness (default: 200mm exterior, 150mm interior)
- Ceiling height (default: 2700mm)

### Step 1 — Define Footprint
```
Standard single-story 120m² house footprint: 12000mm × 10000mm
Rooms laid out on a grid:
  ┌─────────────────────────────────────────┐
  │     Living Room      │    Kitchen        │
  │  (5000×4500mm)      │  (4000×4500mm)   │
  ├──────────┬───────────┴─────────────────-─┤
  │ Corridor │  Bedroom 1   │  Bedroom 2     │
  │(1500×5500)│ (5000×3500) │ (4000×3500mm) │
  │          ├─────────────────────────┤
  │          │     Bathroom (3000×2500mm)    │
  └──────────┴──────────────────────────────┘
```

### Step 2 — Build in Order
1. Create document
2. Build exterior walls first (closed rectangle)
3. Add interior partition walls
4. Add floor object grouping all walls
5. Add doors (exterior entry + interior room doors)
6. Add windows (living room, bedrooms, kitchen)
7. Add roof
8. Group into building → site
9. Save and export

### Step 3 — Validate Each Step
After each major step, run:
```python
_result_ = [{
    "name": obj.Name,
    "label": obj.Label,
    "type": obj.TypeId,
    "valid": obj.Shape.isValid() if hasattr(obj, 'Shape') else True
} for obj in doc.Objects]
```

---

## ERROR DIAGNOSIS GUIDE

| Error | Cause | Fix |
|-------|-------|-----|
| `AttributeError: 'NoneType' has no attribute...` | `doc.recompute()` not called after object creation | Add `doc.recompute()` after every object creation |
| `Wall has no shape` | Base line not computed before wall creation | Ensure `doc.recompute()` after `Draft.makeLine()` |
| `Object not found` | Wrong object name or document | Use `doc.getObject(name)` and check it's not None |
| `Cannot import Arch` | BIM workbench not active | Add `import Arch` explicitly; it works headless |
| `makeWall needs a base` | Passing None as base | Use `Draft.makeLine()` first, then pass to makeWall |
| `Placement error` | Wrong Vector/Rotation args | FreeCAD.Vector(x,y,z) — all floats, not ints |
| `Roof fails` | Invalid wire | Use simple rectangle wire: `Part.makePolygon([p1,p2,p3,p4,p1])` |
| `recompute error` | Circular dependency | Delete conflicting objects and rebuild |

---

## EXECUTION PATTERN FOR EACH TOOL CALL

Always structure `execute_python` calls like this:

```python
# 1. Imports at top
import FreeCAD, Draft, Arch, Part

# 2. Get or create document
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("House")

# 3. Do the work
# ... your code ...

# 4. Always recompute
doc.recompute()

# 5. Always set _result_ to confirm success
_result_ = {
    "status": "ok",
    "objects_created": [...],
    "message": "Step X complete"
}
```

---

## STANDARD HOUSE DIMENSIONS (mm)

| Element | Min | Standard | Large |
|---------|-----|----------|-------|
| Exterior wall thickness | 150 | 200 | 300 |
| Interior wall thickness | 100 | 150 | 200 |
| Ceiling height | 2400 | 2700 | 3000 |
| Door width | 800 | 900 | 1000 |
| Door height | 2000 | 2100 | 2200 |
| Window width | 600 | 1200 | 1800 |
| Window height | 900 | 1200 | 1500 |
| Window sill height | 800 | 900 | 1000 |
| Corridor width | 900 | 1200 | 1500 |
| Stair width | 900 | 1000 | 1200 |
| Tread depth | 250 | 280 | 300 |
| Riser height | 160 | 175 | 190 |

All dimensions in **millimeters**. FreeCAD's default unit is mm.
