"""Standalone validation must not reset the caller's data-loader budget.

The model fixtures exercise OpenScrub's real train/export/publication flow,
not GPU training. In particular the reloaded model has no training overrides.
"""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from test_plate_seg_training import dataset  # noqa: F401 -- shared fixture
from scripts import train_plate_seg as training


@pytest.fixture
def run_case(dataset, tmp_path, monkeypatch):
    root, _ = dataset
    weights = tmp_path / "source-seg.pt"
    weights.write_bytes(b"synthetic checkpoint; never deserialized")
    calls = []
    scores = {"map50": .78, "map": .52}

    class Model:
        task = "segment"

        def __init__(self, path):
            self.path = Path(path)
            calls.append(("load", self.path))

        def train(self, **kwargs):
            calls.append(("train", kwargs))
            folder = Path(kwargs["project"]) / "training" / "weights"
            folder.mkdir(parents=True)
            (folder / "best.pt").write_bytes(b"synthetic trained checkpoint")

        def val(self, **kwargs):
            calls.append(("val", kwargs))
            return SimpleNamespace(seg=SimpleNamespace(**scores),
                                   box=SimpleNamespace(map50=.8))

        def export(self, **kwargs):
            calls.append(("export", kwargs))
            result = self.path.with_suffix(".onnx")
            result.write_bytes(b"synthetic graph")
            return str(result)

    monkeypatch.setitem(sys.modules, "ultralytics",
                        SimpleNamespace(YOLO=Model, __version__="fixture"))
    monkeypatch.setattr(training, "_cuda_info",
                        lambda device: {"torch": "fixture", "cuda": "fixture",
                                        "gpu": "synthetic device"})
    monkeypatch.setattr(training, "_smoke_onnx", lambda *args: {})
    args = argparse.Namespace(
        weights=weights, accept_ultralytics_license=True, epochs=1,
        batch=8, imgsz=640, workers=0, patience=1, seed=42, device=0,
        min_mask_map50=.25, versions_dir=tmp_path / "versions", dataset=root,
        min_train_positive=12, min_val_positive=4, min_negative_per_split=1)
    return args, training.validate_dataset(root), calls, scores


@pytest.mark.parametrize("workers,batch,imgsz", [(0, 8, 640), (2, 3, 320)])
def test_reloaded_validation_honors_training_resource_budget(run_case, workers, batch, imgsz):
    args, report, calls, _ = run_case
    args.workers, args.batch, args.imgsz = workers, batch, imgsz
    result = training.train(args, report)
    train = next(kwargs for name, kwargs in calls if name == "train")
    val = next(kwargs for name, kwargs in calls if name == "val")
    # A distinct best.pt model is reloaded: its defaults must not select workers.
    assert len([name for name, _ in calls if name == "load"]) == 2
    for key, expected in {"workers": workers, "batch": batch, "imgsz": imgsz,
                          "device": 0, "cache": False}.items():
        assert train[key] == expected
        assert val.get(key) == expected, (key, val)
    assert val["split"] == "val" and val["data"] == train["data"]
    assert result["deployment"] == "not_activated"
    assert training.verify_version(args.versions_dir, result["version"])["validation"]["mask_map50"] == .78
    assert not (args.versions_dir / ".training.lock").exists()


def test_direct_metrics_defaults_do_not_spawn_workers(tmp_path):
    seen = {}
    class Model:
        def val(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(seg=SimpleNamespace(map50=.6, map=.4))
    assert training._metrics(Model(), tmp_path / "data.yaml", 0, tmp_path) == {
        "mask_map50": .6, "mask_map": .4}
    assert seen.get("workers") == 0
    assert seen.get("batch") == 8
    assert seen.get("imgsz") == 640
    assert seen.get("cache") is False


@pytest.mark.parametrize("score", [.1, float("nan"), float("inf")])
def test_resource_fix_does_not_bypass_quality_gate(run_case, score):
    args, report, calls, scores = run_case
    scores["map50"] = score
    with pytest.raises(RuntimeError, match="below|Non-finite"):
        training.train(args, report)
    assert not any(name == "export" for name, _ in calls)
    assert not (args.versions_dir / "index.json").exists()
    assert not list(args.versions_dir.glob(".staging-*"))
    assert not (args.versions_dir / ".training.lock").exists()


def test_training_compose_uses_bounded_private_shared_memory():
    root = Path(__file__).resolve().parent
    service = yaml.safe_load((root / "compose.windows-training.yml").read_text())["services"]["openscrub"]
    assert service.get("shm_size") == "1gb"
    assert service.get("ipc") != "host"
    # This opt-in overlay must not replace any persistent data or media mount.
    assert "volumes" not in service
    assert service["environment"]["OPENSCRUB_TRAIN_PYTHON"] == "/opt/openscrub-training/bin/python"
    for name in ("compose.windows-test.yml", "compose.windows-cuda.yml"):
        base = yaml.safe_load((root / name).read_text())["services"]["openscrub"]
        assert "shm_size" not in base
