"""Local validation only: unset output setting after canonical startup."""
import json
import os
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def fallback_media_output(request, monkeypatch):
    names = ("test_old_report_production_pixels_and_independent_pts", "test_native_coarse_timebase_production_pixels_pts", "test_retained_strict_route_and_actual_engine_priming")
    if request.node.originalname not in names:
        yield
        return
    run = Path(os.environ["VERIFY_RUN"])
    monkeypatch.delenv("VERIFY_RUN")
    temporary = request.getfixturevalue("tmp_path")
    yield
    outputs = sorted(str(p) for p in (temporary / "artifacts").glob("*.json"))
    with (run / "logs" / "fallback-locations.jsonl").open("a") as record:
        record.write(json.dumps({"node": request.node.nodeid, "directory": str(temporary / "artifacts"), "outputs": outputs}) + "\n")
