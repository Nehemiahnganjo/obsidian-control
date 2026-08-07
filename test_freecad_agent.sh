#!/usr/bin/env bash
# test_freecad_agent.sh — Auto-starts FreeCAD, waits for bridge, runs house plan test
# Usage: bash test_freecad_agent.sh

set -euo pipefail

FREECAD_BIN="/usr/bin/FreeCAD"
BRIDGE_PORT=9875
PROJECTS_DIR="$HOME/obsidian_control/freecad_projects"
LOG="$HOME/obsidian_control/freecad_test.log"
TIMEOUT=60  # seconds to wait for FreeCAD bridge

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }
step()  { echo -e "\n${YELLOW}━━━ $* ━━━${NC}"; }

mkdir -p "$PROJECTS_DIR"

# ── Step 1: Check if bridge already running ───────────────────────────────────
step "1 / 5  Check FreeCAD XML-RPC bridge"

bridge_running() {
    python3 -c "
import xmlrpc.client, sys
try:
    p = xmlrpc.client.ServerProxy('http://localhost:${BRIDGE_PORT}')
    p.execute('_result_ = True')
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null
}

if bridge_running; then
    info "Bridge already running on port $BRIDGE_PORT"
else
    warn "Bridge not running — starting FreeCAD headless bridge..."

    # Start FreeCADCmd with the XML-RPC bridge script
    FreeCADCmd -c "
import sys; sys.argv = []
exec(open('/home/void/obsidian_control/freecad_xmlrpc_bridge.py').read())
" >>"$LOG" 2>&1 &
    FREECAD_PID=$!
    info "FreeCAD bridge started (PID $FREECAD_PID)"

    # Wait for bridge
    echo -n "    Waiting for XML-RPC bridge"
    elapsed=0
    while ! bridge_running; do
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
        if [[ $elapsed -ge $TIMEOUT ]]; then
            echo ""
            error "Timed out waiting for bridge after ${TIMEOUT}s"
            echo ""
            echo "  Possible reasons:"
            echo "  1. FreeCAD didn't load the RobustMCPBridge workbench"
            echo "  2. Display not available (try: export DISPLAY=:0)"
            echo "  3. Bridge workbench error — check FreeCAD console"
            echo ""
            echo "  Manual fix:"
            echo "  - Open FreeCAD"
            echo "  - Switch to 'MCP Bridge' workbench"
            echo "  - Bridge starts automatically"
            echo ""
            echo "  Then re-run this script."
            exit 1
        fi
    done
    echo ""
    info "Bridge ready on port $BRIDGE_PORT (waited ${elapsed}s)"
fi

# ── Step 2: Verify freecad-mcp binary works ───────────────────────────────────
step "2 / 5  Verify freecad-mcp MCP server"

MCP_BIN="$HOME/freecad-mcp-venv/bin/freecad-mcp"
if [[ ! -f "$MCP_BIN" ]]; then
    error "freecad-mcp not found at $MCP_BIN"
    exit 1
fi

# Quick connection test via Python xmlrpc
python3 - <<'PYEOF'
import xmlrpc.client, json, sys
p = xmlrpc.client.ServerProxy('http://localhost:9875')
result = p.execute("""
import FreeCAD, sys
_result_ = {
    'freecad_version': '.'.join(str(x) for x in FreeCAD.Version()[:3]),
    'python_version': sys.version.split()[0],
    'gui_up': FreeCAD.GuiUp,
}
""")
if result['success']:
    d = result['result']
    print(f"    FreeCAD {d['freecad_version']} | Python {d['python_version']} | GUI: {d['gui_up']}")
else:
    print(f"    ERROR: {result['stderr']}", file=sys.stderr)
    sys.exit(1)
PYEOF
info "FreeCAD connection verified"

# ── Step 3: Check Arch/BIM modules available ──────────────────────────────────
step "3 / 5  Verify BIM/Arch modules"

python3 - <<'PYEOF'
import xmlrpc.client, sys
p = xmlrpc.client.ServerProxy('http://localhost:9875')
result = p.execute("""
import FreeCAD
available = []
missing = []
for mod in ['Draft', 'Arch', 'Part', 'Mesh', 'TechDraw']:
    try:
        __import__(mod)
        available.append(mod)
    except ImportError:
        missing.append(mod)
_result_ = {'available': available, 'missing': missing}
""")
if result['success']:
    d = result['result']
    print(f"    Available: {', '.join(d['available'])}")
    if d['missing']:
        print(f"    Missing:   {', '.join(d['missing'])}", file=sys.stderr)
else:
    print(f"    ERROR: {result['stderr']}", file=sys.stderr)
    sys.exit(1)
PYEOF
info "BIM modules verified"

# ── Step 4: Run basic house build test ────────────────────────────────────────
step "4 / 5  Build test house plan"

python3 - <<PYEOF
import xmlrpc.client, json, sys, os

p = xmlrpc.client.ServerProxy('http://localhost:9875')
projects_dir = os.path.expanduser('~/obsidian_control/freecad_projects')

# ── Test: build a simple 2-bedroom house footprint ────────────────────────────
code = '''
import FreeCAD, Draft, Arch, Part

# Create fresh document
for name in list(FreeCAD.listDocuments().keys()):
    FreeCAD.closeDocument(name)

doc = FreeCAD.newDocument("TestHouse")
doc.Label = "Test House — 2 Bedroom"

W = 200    # exterior wall thickness mm
IW = 150   # interior wall thickness mm
H = 2700   # ceiling height mm

# ── Exterior shell: 10m x 8m ─────────────────────────────────────────────────
ext_pts = [
    [(0,0,0),     (10000,0,0)],    # South wall
    [(10000,0,0), (10000,8000,0)], # East wall
    [(10000,8000,0),(0,8000,0)],   # North wall
    [(0,8000,0),  (0,0,0)],        # West wall
]
ext_walls = []
for i, (p1, p2) in enumerate(ext_pts):
    line = Draft.makeLine(FreeCAD.Vector(*p1), FreeCAD.Vector(*p2))
    doc.recompute()
    wall = Arch.makeWall(line, width=W, height=H)
    wall.Label = f"ExtWall_{i+1}"
    ext_walls.append(wall)
    doc.recompute()

# ── Interior partitions ───────────────────────────────────────────────────────
int_defs = [
    # Living / Kitchen divider: x=5500, y=0..5000
    [(5500,0,0),    (5500,5000,0)],
    # Corridor wall: y=5000, x=0..10000
    [(0,5000,0),    (10000,5000,0)],
    # Bedroom divider: x=5000, y=5000..8000
    [(5000,5000,0), (5000,8000,0)],
    # Bathroom wall: x=7000, y=5000..8000
    [(7000,5000,0), (7000,8000,0)],
]
int_walls = []
for i, (p1, p2) in enumerate(int_defs):
    line = Draft.makeLine(FreeCAD.Vector(*p1), FreeCAD.Vector(*p2))
    doc.recompute()
    wall = Arch.makeWall(line, width=IW, height=H)
    wall.Label = f"IntWall_{i+1}"
    int_walls.append(wall)
    doc.recompute()

all_walls = ext_walls + int_walls

# ── Floor level ───────────────────────────────────────────────────────────────
floor = Arch.makeFloor(all_walls)
floor.Label = "GroundFloor"
floor.Height = H
doc.recompute()

# ── Building + Site ───────────────────────────────────────────────────────────
building = Arch.makeBuilding([floor])
building.Label = "TestHouse"
site = Arch.makeSite([building])
site.Label = "Site"
doc.recompute()

# ── Flat roof slab ────────────────────────────────────────────────────────────
slab = doc.addObject("Part::Box", "RoofSlab")
slab.Length = 10000.0
slab.Width  = 8000.0
slab.Height = 200.0
slab.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, float(H)),
    FreeCAD.Rotation()
)
doc.recompute()

# ── Save FCStd ────────────────────────────────────────────────────────────────
import os
out = os.path.join("''' + projects_dir + '''", "test_house.FCStd")
doc.saveAs(out)

# ── Count objects ─────────────────────────────────────────────────────────────
_result_ = {
    "status": "ok",
    "objects": [{"name": o.Name, "type": o.TypeId} for o in doc.Objects],
    "saved_to": out,
    "wall_count": len(all_walls),
}
'''

print("    Running FreeCAD house build script...")
result = p.execute(code)

if result['success'] and result['result']:
    r = result['result']
    print(f"    Status    : {r['status']}")
    print(f"    Walls     : {r['wall_count']} ({4} exterior + {4} interior)")
    print(f"    Objects   : {len(r['objects'])}")
    print(f"    Saved to  : {r['saved_to']}")
    for o in r['objects']:
        print(f"              • {o['name']:20s}  {o['type']}")
else:
    print(f"    ERROR: {result.get('stderr','')}", file=sys.stderr)
    if result.get('error_traceback'):
        print(result['error_traceback'], file=sys.stderr)
    sys.exit(1)
PYEOF

if [[ $? -eq 0 ]]; then
    info "House plan built successfully"
else
    error "House plan build FAILED — see errors above"
    exit 1
fi

# ── Step 5: Summary ───────────────────────────────────────────────────────────
step "5 / 5  Done"

info "All tests passed"
echo ""
echo "  Files saved to: $PROJECTS_DIR"
ls -lh "$PROJECTS_DIR" 2>/dev/null || true
echo ""
echo "  To use the freecad agent:"
echo "    kiro-cli chat --agent freecad \"Design a 3-bedroom house with open plan living\""
echo ""
echo "  Or via Telegram — switch to freecad agent:"
echo "    /new freecad_work freecad /home/void/obsidian_control/freecad_projects"
echo "    Then send: 'Design a house with 3 bedrooms, 2 bathrooms, open plan kitchen'"
