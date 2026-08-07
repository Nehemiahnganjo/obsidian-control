"""
mcp_bridge_server.py — XML-RPC server that runs inside FreeCAD
Listens on localhost:9875, exposes execute() method.
Compatible with freecad-robust-mcp xmlrpc bridge.
"""

from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import traceback
import sys
import io


class QuietHandler(SimpleXMLRPCRequestHandler):
    def log_message(self, format, *args):
        pass


# Persistent namespace across calls
_exec_namespace = {}
_server = None


def execute(code: str) -> dict:
    """Execute Python code in FreeCAD context. Returns result dict."""
    import FreeCAD

    stdout_cap = io.StringIO()
    stderr_cap = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr

    result_val = None
    success = False
    error_type = None
    error_tb = None

    try:
        sys.stdout = stdout_cap
        sys.stderr = stderr_cap

        _exec_namespace.update({"FreeCAD": FreeCAD, "App": FreeCAD})

        try:
            import FreeCADGui
            _exec_namespace["FreeCADGui"] = FreeCADGui
            _exec_namespace["Gui"] = FreeCADGui
        except Exception:
            pass

        for mod in ["Part", "Draft", "Arch", "Mesh", "Sketcher",
                    "MeshPart", "TechDraw", "Spreadsheet", "ArchWall",
                    "ArchFloor", "ArchBuilding", "ArchRoof", "ArchWindow",
                    "ArchStairs", "ArchSpace", "ArchSectionPlane"]:
            try:
                _exec_namespace[mod] = __import__(mod)
            except Exception:
                pass

        _exec_namespace["_result_"] = None
        exec(code, _exec_namespace)  # noqa: S102
        result_val = _exec_namespace.get("_result_")
        success = True

    except Exception as e:
        error_type = type(e).__name__
        error_tb = traceback.format_exc()

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "success": success,
        "result": result_val,
        "stdout": stdout_cap.getvalue(),
        "stderr": stderr_cap.getvalue(),
        "error_type": error_type,
        "error_traceback": error_tb,
    }


def start(host: str = "localhost", port: int = 9875):
    global _server
    _server = SimpleXMLRPCServer(
        (host, port),
        requestHandler=QuietHandler,
        allow_none=True,
        logRequests=False,
    )
    _server.register_function(execute, "execute")
    _server.register_introspection_functions()
    _server.serve_forever()


def stop():
    global _server
    if _server:
        _server.shutdown()
        _server = None
