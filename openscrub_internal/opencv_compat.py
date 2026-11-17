"""Read-only OpenCV fallback checks, independent of models and providers."""
import json
import os
import re
import shlex
import subprocess

_FLAVORS = ("opencv-python", "opencv-contrib-python", "opencv-python-headless",
            "opencv-contrib-python-headless")
_CAPABILITIES = {"ok", "unavailable", "missing_api", "missing_xml",
                 "classifier_error", "empty_classifier"}

# Self-contained: a frozen installer may select a Python without OpenScrub.
_PROBE = r'''
# OPENSCRUB_OPENCV_PROBE
import importlib.metadata
import json
import os
result = dict(status="ok", version=None, path=None, distributions={},
              capability="unavailable", detail="")
try:
    import cv2
except ModuleNotFoundError as exc:
    result.update(status="missing_import" if exc.name == "cv2" else "import_error", detail=str(exc))
except Exception as exc:
    result.update(status="import_error", detail=str(exc))
else:
    result.update(version=str(getattr(cv2, "__version__", "")),
                  path=str(getattr(cv2, "__file__", "")))
    if not callable(getattr(cv2, "CascadeClassifier", None)):
        result["capability"] = "missing_api"
    else:
        root = getattr(getattr(cv2, "data", None), "haarcascades", "")
        try:
            if not root:
                raise OSError("cv2.data.haarcascades unavailable")
            xml = os.path.join(root, "haarcascade_frontalface_default.xml")
            with open(xml, "rb") as stream:
                if not stream.read(1):
                    raise OSError("Haar XML is empty")
        except (OSError, TypeError, ValueError) as exc:
            result.update(capability="missing_xml", detail=str(exc))
        else:
            try:
                cascade = cv2.CascadeClassifier(xml)
                result["capability"] = "empty_classifier" if cascade.empty() else "ok"
            except Exception as exc:
                result.update(capability="classifier_error", detail=str(exc))
for name in ("opencv-python", "opencv-contrib-python", "opencv-python-headless", "opencv-contrib-python-headless"):
    try:
        result["distributions"][name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
    except Exception as exc:
        result.update(status="metadata_error", detail=str(exc))
print(json.dumps(result))
'''


def _failure(status, detail):
    return dict(status=status, version=None, path=None, distributions={},
                capability="unavailable", detail=detail)


def probe_opencv(python_executable):
    """Collect fresh target-interpreter facts; never import cv2 in this process."""
    try:
        child = subprocess.run([python_executable, "-c", _PROBE],
                               capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return _failure("timeout", "OpenCV probe exceeded 15 seconds")
    except OSError as exc:
        return _failure("launch_error", str(exc))
    if child.returncode:
        return _failure("crash", "exit %s: %s" % (child.returncode, (child.stderr or "")[-500:]))
    try:
        result = json.loads(child.stdout)
        if not isinstance(result, dict) or set(result) != {
                "status", "version", "path", "distributions", "capability", "detail"}:
            raise ValueError("unexpected probe fields")
        if result["status"] not in {"ok", "missing_import", "import_error", "metadata_error"}:
            raise ValueError("unknown probe status")
        if result["capability"] not in _CAPABILITIES:
            raise ValueError("unknown fallback result")
        if not isinstance(result["distributions"], dict) or any(
                k not in _FLAVORS or not isinstance(v, str)
                for k, v in result["distributions"].items()):
            raise ValueError("invalid distribution metadata")
        if any(v is not None and not isinstance(v, str)
               for v in (result["version"], result["path"])) or not isinstance(result["detail"], str):
            raise ValueError("invalid runtime metadata")
        if result["status"] == "ok" and not result["path"]:
            raise ValueError("missing runtime metadata")
        return result
    except (ValueError, TypeError, KeyError):
        return _failure("malformed_output", "OpenCV probe returned invalid JSON evidence")


def _version(value):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.\d+)?(?:[-+].*)?", value or "")
    return tuple(map(int, match.groups())) if match else None


def assess_opencv(snapshot):
    """Separate fallback capability from wheel ownership and core policy."""
    distributions = snapshot["distributions"]
    usable = snapshot["status"] in {"ok", "metadata_error"} and snapshot["capability"] == "ok"
    runtime = _version(snapshot["version"])
    versions = [_version(v) for v in distributions.values()]
    if len(distributions) > 1:
        state = "conflict"
    elif snapshot["status"] in {"timeout", "crash", "malformed_output", "metadata_error", "launch_error"}:
        state = "uncertain"
    elif snapshot["status"] == "missing_import" and not distributions:
        state = "missing"
    elif any(v and v[0] >= 5 for v in [runtime] + versions):
        state = "unsupported"
    elif any(v is None for v in versions):
        state = "uncertain"
    elif snapshot["status"] in {"import_error", "missing_import"}:
        state = "broken"
    elif runtime is None:
        state = "uncertain"
    elif versions and runtime != versions[0]:
        state = "uncertain"
    elif not usable:
        state = "broken"
    elif not distributions:
        state = "unmanaged"
    elif "opencv-python" not in distributions:
        state = "alternate"
    else:
        state = "healthy"
    evidence = "runtime=%s; path=%s; wheels=%s; fallback=%s; probe=%s" % (
        snapshot["version"] or "unknown", snapshot["path"] or "unknown",
        ", ".join("%s==%s" % pair for pair in distributions.items()) or "none (source/distro/frozen or absent)",
        snapshot["capability"], snapshot["status"])
    if snapshot["detail"]:
        evidence += "; " + snapshot["detail"]
    return dict(state=state, fallback_usable=usable, healthy=state == "healthy", evidence=evidence)


def opencv_repair_hint(snapshot, python_executable):
    """Print a deliberate repair only when a sole normal wheel is identified."""
    assessment = assess_opencv(snapshot)
    state = assessment["state"]
    command = subprocess.list2cmdline([python_executable]) if os.name == "nt" else shlex.quote(python_executable)
    rerun = "Rerun health checks in a fresh process: %s -m openscrub_setup --check (source: %s install.py --check)." % (command, command)
    if state == "healthy":
        return ""
    if state in {"unsupported", "broken"} and set(snapshot["distributions"]) == {"opencv-python"}:
        return ('To deliberately restore the compatible normal wheel, run: %s -m pip install --force-reinstall "opencv-python<5". ' % command) + rerun
    if state == "missing":
        return ('Install the core requirement with %s -m pip install "opencv-python<5". ' % command) + rerun
    return ("Reconcile cv2 ownership deliberately or use a clean core environment. "
            "Alternate wheels and unmanaged source/distro/frozen builds are not the normal managed wheel; "
            "for source-built CUDA OpenCV, verify the source build includes CascadeClassifier and readable Haar XML. "
            "Do not add another wheel flavor to repair mixed or uncertain ownership. " + rerun)
