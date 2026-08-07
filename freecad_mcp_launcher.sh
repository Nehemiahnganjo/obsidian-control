#!/usr/bin/env bash
# freecad_mcp_launcher.sh
# Ensures the FreeCAD XML-RPC bridge is running, then starts the freecad-mcp MCP server.
# Used as the command for the freecad MCP server in kiro's mcp.json.

BRIDGE_SCRIPT="$HOME/obsidian_control/freecad_xmlrpc_bridge.py"
BRIDGE_PORT="${FREECAD_XMLRPC_PORT:-9875}"
MCP_BIN="$HOME/freecad-mcp-venv/bin/freecad-mcp"
LOG="$HOME/obsidian_control/freecad_bridge.log"

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

# Start the FreeCAD XML-RPC bridge if not already running
if ! bridge_running; then
    FreeCADCmd -c "
import sys; sys.argv = []
exec(open('${BRIDGE_SCRIPT}').read())
" >>"$LOG" 2>&1 &
    BRIDGE_PID=$!
    echo "[freecad-mcp] Started FreeCAD bridge (PID $BRIDGE_PID)" >&2

    # Wait up to 15s for bridge
    for i in $(seq 1 15); do
        sleep 1
        if bridge_running; then
            echo "[freecad-mcp] Bridge ready on port $BRIDGE_PORT" >&2
            break
        fi
        if [[ $i -eq 15 ]]; then
            echo "[freecad-mcp] ERROR: Bridge did not start in 15s" >&2
            exit 1
        fi
    done
else
    echo "[freecad-mcp] Bridge already running on port $BRIDGE_PORT" >&2
fi

# Start the MCP server
exec "$MCP_BIN" \
    --mode xmlrpc \
    --transport stdio \
    "$@"
