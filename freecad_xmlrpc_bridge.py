"""
freecad_xmlrpc_bridge.py
Run via: FreeCADCmd -c "exec(open('/path/to/this').read())"
Or:      FreeCADCmd freecad_xmlrpc_bridge.py

Starts an XML-RPC server on localhost:9875 inside FreeCAD's Python environment.
All FreeCAD modules (Draft, Arch, Part, etc.) are available.
Compatible with freecad-robust-mcp in xmlrpc mode.
"""

from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import traceback
import threading
import sys
import io
import os

HOST = os.environ.get("FREECAD_BRIDGE_HOST", "localhost")
PORT = int(os.environ.get("FREECAD_XMLRPC_PORT", "9875"))

# Persistent exec namespace — survives across calls
_ns = {}
_ns_lock = threading.Lock()


class QuietHandler(SimpleXMLRPCRequestHandler):
    def log_message(self, *a):
        pass


def _bootstrap_namespace():
    """Pre-load all FreeCAD modules into namespace."""
    import FreeCAD
    _ns.update({"FreeCAD": FreeCAD, "App": FreeCAD})

    mods = ["Part", "Draft", "Arch", "Mesh", "Sketcher",
            "MeshPart", "TechDraw", "Spreadsheet",
            "ArchWall", "ArchFloor", "ArchBuilding",
            "ArchRoof", "ArchWindow", "ArchStairs",
            "ArchSpace", "ArchSectionPlane", "Import"]

    for name in mods:
        try:
            _ns[name] = __import__(name)
        except ImportError:
            pass

    # Try GUI modules (only available in GUI mode)
    try:
        import FreeCADGui
        _ns["FreeCADGui"] = FreeCADGui
        _ns["Gui"] = FreeCADGui
    except ImportError:
        pass


def execute(code: str) -> dict:
    """Execute Python code in FreeCAD context. Thread-safe."""
    stdout_cap = io.StringIO()
    stderr_cap = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr

    result_val = None
    success = False
    error_type = None
    error_tb = None

    with _ns_lock:
        try:
            sys.stdout = stdout_cap
            sys.stderr = stderr_cap

            _ns["_result_"] = None
            exec(code, _ns)  # noqa: S102
            result_val = _ns.get("_result_")
            success = True

        except Exception as e:
            error_type = type(e).__name__
            error_tb = traceback.format_exc()

        finally:
            sys.stdout = old_out
            sys.stderr = old_err

    return {
        "success": success,
        "result": result_val,
        "stdout": stdout_cap.getvalue(),
        "stderr": stderr_cap.getvalue(),
        "error_type": error_type,
        "error_traceback": error_tb,
    }


def main():
    _bootstrap_namespace()

    server = SimpleXMLRPCServer(
        (HOST, PORT),
        requestHandler=QuietHandler,
        allow_none=True,
        logRequests=False,
    )
    server.register_function(execute, "execute")
    server.register_introspection_functions()

    print(f"[FreeCAD MCP Bridge] XML-RPC ready at http://{HOST}:{PORT}", flush=True)
    print(f"[FreeCAD MCP Bridge] Modules: {[k for k in _ns if not k.startswith('_')]}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
