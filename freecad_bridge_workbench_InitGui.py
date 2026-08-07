"""
RobustMCPBridge — FreeCAD Workbench
Starts an XML-RPC server on port 9875 when FreeCAD launches.
Allows freecad-robust-mcp (and kiro) to control FreeCAD remotely.
"""
import FreeCADGui
import FreeCAD


class RobustMCPBridgeWorkbench(FreeCADGui.Workbench):
    MenuText = "MCP Bridge"
    ToolTip = "Robust MCP Bridge — XML-RPC server on port 9875"
    Icon = ""

    def Initialize(self):
        self.appendMenu("MCP Bridge", [])

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(RobustMCPBridgeWorkbench())

# Auto-start the XML-RPC server
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

try:
    import mcp_bridge_server
    t = threading.Thread(target=mcp_bridge_server.start, daemon=True)
    t.start()
    FreeCAD.Console.PrintMessage("[MCP Bridge] XML-RPC server started on port 9875\n")
except Exception as e:
    FreeCAD.Console.PrintError(f"[MCP Bridge] Failed to start: {e}\n")
