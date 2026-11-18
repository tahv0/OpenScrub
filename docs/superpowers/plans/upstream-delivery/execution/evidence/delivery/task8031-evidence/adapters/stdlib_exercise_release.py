
import builtins
import contextlib
import io
import sys
import sysconfig
from pathlib import Path
import importlib.util
from types import ModuleType
original_import = builtins.__import__
stdlib = Path(sysconfig.get_path("stdlib")).resolve()
def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if level == 0 and root != "openscrub_internal":
        spec = importlib.util.find_spec(root)
        if (spec is None and name == "org.python.core" and globals
                and globals.get("__name__") == "copy"
                and Path(globals.get("__file__", "")).resolve() == (stdlib / "copy.py").resolve()):
            # CPython 3.9 copy probes Jython support and catches ImportError.
            raise ModuleNotFoundError("optional Jython support unavailable")
        origin = None if spec is None else spec.origin
        if origin not in ("built-in", "frozen"):
            path = None if not origin else Path(origin).resolve()
            if path is None or stdlib not in path.parents or "site-packages" in path.parts:
                raise AssertionError("non-stdlib import attempted: " + root)
    if name.startswith("openscrub_internal") and name not in (
        "openscrub_internal", "openscrub_internal.plate_search",
        "openscrub_internal.plate_search.matching"):
        raise AssertionError("other internal module attempted")
    if name == "openscrub_internal" and any(part != "plate_search" for part in fromlist):
        raise AssertionError("other internal import attempted")
    if name == "openscrub_internal.plate_search" and any(part != "matching" for part in fromlist):
        raise AssertionError("other plate_search import attempted")
    return original_import(name, globals, locals, fromlist, level)
# A cached app module must still be rejected before import can return it.
previous = sys.modules.get("openscrub")
cached = ModuleType("openscrub")
cached.__spec__ = importlib.util.spec_from_file_location("openscrub", "/unavailable/openscrub.py")
sys.modules["openscrub"] = cached
try:
    for forbidden, caller in [
        ("openscrub", {"__name__": "__main__"}),
        ("org.python.core", {"__name__": "__main__"}),
        ("org.python.core", {"__name__": "copy", "__file__": "/unavailable/copy.py"}),
    ]:
        try:
            restricted_import(forbidden, caller)
        except AssertionError:
            pass
        else:
            raise AssertionError("blocker accepted a forbidden import")
finally:
    if previous is None:
        del sys.modules["openscrub"]
    else:
        sys.modules["openscrub"] = previous
builtins.__import__ = restricted_import
product_stdout, product_stderr = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(product_stdout), contextlib.redirect_stderr(product_stderr):
    from openscrub_internal.plate_search.matching import normalize_queries, match_text
    assert match_text("ab-c123", normalize_queries("ABC123"))[0].match_kind == "full_equal"
    assert not match_text("XABC123Y", normalize_queries("ABC123"))
    assert match_text("XABC123Y", normalize_queries("ABC123", mode="fragment"))[0].match_kind == "fragment"
assert product_stdout.getvalue() == ""
assert product_stderr.getvalue() == ""
