"""Offline tests for local OpenScrub CUDA segmentation training utilities.

These tests do not require a GPU, Ultralytics or a downloaded checkpoint.
Run: pytest -q test_plate_seg_training.py
"""
import argparse
import copy
import json
import shutil
import sys
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import train_plate_seg as training


def _sample(root, split, index, label="positive", quality=None, track=None,
            group_job="testrecording"):
    folder = root / "images" / split
    label_dir = root / "labels" / split
    folder.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    name = "sample_%s_%03d" % (split, index)
    # Rich, distinct deterministic texture ensures the dHash check tests
    # duplicate leakage rather than flags synthetic plain-color images.
    rng = np.random.default_rng(index + (0 if split == "train" else 1000))
    img = rng.integers(10, 240, (72, 128, 3), dtype=np.uint8)
    cv2.rectangle(img, (35, 24), (98, 48), (255, 255, 250), -1)
    cv2.imwrite(str(folder / (name + ".jpg")), img)
    (label_dir / (name + ".txt")).write_text(
        "0 .27 .33 .77 .33 .76 .66 .28 .67\n"
        if label == "positive" else "", encoding="utf-8")
    return {"image": "images/%s/%s.jpg" % (split, name),
            "label": label,
            "quality": quality or (
                "human_quad" if label == "positive"
                else "human_hard_negative"),
            "split": split, "job": group_job,
            "track": index if track is None else track,
            "detection_index": index}


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "plate-seg"
    root.mkdir()
    rows = []
    for i in range(14):
        rows.append(_sample(root, "train", i))
    for i in range(4):
        rows.append(_sample(root, "val", i + 20))
    for i in range(3):
        rows.append(_sample(root, "train", i + 40, "negative"))
    for i in range(2):
        rows.append(_sample(root, "val", i + 50, "negative"))
    (root / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (root / "data.yaml").write_text(
        "path: " + str(root) + "\ntrain: images/train\n"
        "val: images/val\nnames:\n  0: plate\n", encoding="utf-8")
    return root, rows


def _write_rows(root, rows):
    (root / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_checked_dataset_and_stable_fingerprint(dataset):
    root, rows = dataset
    report = training.validate_dataset(root)
    assert report["samples"] == len(rows)
    assert report["counts"]["train"]["positive"] == 14
    assert report["counts"]["val"]["negative"] == 2
    assert report["unique_track_groups"] == len(rows)
    assert report["dataset_sha256"] == training.validate_dataset(
        root)["dataset_sha256"]
    assert "unseen video" in report["warning"]


@pytest.mark.parametrize("bad_quality", ["human_bbox_weak", "auto_tracked",
                                       "default_enabled"])
def test_weak_and_automatic_labels_rejected(dataset, bad_quality):
    root, rows = dataset
    changed = copy.deepcopy(rows)
    changed[0]["quality"] = bad_quality
    _write_rows(root, changed)
    with pytest.raises(training.DataError, match="Unverified/weak"):
        training.validate_dataset(root)


def test_rejects_invalid_four_point_geometry(dataset):
    root, rows = dataset
    label_path = root / "labels" / "train" / (
        Path(rows[0]["image"]).stem + ".txt")
    label_path.write_text("0 0.1 0.1 0.8 0.8 0.1 0.8 0.8 0.1\n",
                          encoding="utf-8")
    with pytest.raises(training.DataError, match="Invalid 4-point"):
        training.validate_dataset(root)


def test_rejects_track_leakage_across_train_val(dataset):
    root, rows = dataset
    changed = copy.deepcopy(rows)
    changed[14]["track"] = changed[0]["track"]
    _write_rows(root, changed)
    with pytest.raises(training.DataError, match="train and val"):
        training.validate_dataset(root)


def test_rejects_cross_split_duplicate_even_if_ids_differ(dataset):
    root, rows = dataset
    a = root / rows[0]["image"]
    b = root / rows[14]["image"]
    shutil.copyfile(a, b)
    with pytest.raises(training.DataError, match="Near-duplicate"):
        training.validate_dataset(root)


def test_rejects_negative_with_positive_polygon(dataset):
    root, rows = dataset
    neg = next(row for row in rows if row["label"] == "negative")
    path = root / "labels" / neg["split"] / (
        Path(neg["image"]).stem + ".txt")
    path.write_text("0 .1 .1 .9 .1 .9 .9 .1 .9\n", encoding="utf-8")
    with pytest.raises(training.DataError, match="Hard negative"):
        training.validate_dataset(root)


def test_rejects_manifest_path_traversal(dataset):
    root, rows = dataset
    changed = copy.deepcopy(rows)
    changed[0]["image"] = "../../unexpected.jpg"
    _write_rows(root, changed)
    with pytest.raises(training.DataError, match="unsafe image"):
        training.validate_dataset(root)


def test_rejects_too_few_confirmed_val_polygons(dataset):
    root, rows = dataset
    with pytest.raises(training.DataError, match="val needs at least 10"):
        training.validate_dataset(root, min_val_positive=10)


def test_cuda_never_falls_back_to_cpu(monkeypatch):
    fake = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False,
                                   device_count=lambda: 0),
        version=types.SimpleNamespace(cuda=None))
    monkeypatch.setitem(sys.modules, "torch", fake)
    with pytest.raises(RuntimeError, match="CUDA unavailable"):
        training._cuda_info(0)


def test_cuda_check_reports_selected_gpu(monkeypatch):
    fake = types.SimpleNamespace(
        __version__="2.fake",
        cuda=types.SimpleNamespace(is_available=lambda: True,
                                   device_count=lambda: 1,
                                   get_device_name=lambda n: "Test GPU"),
        version=types.SimpleNamespace(cuda="12.x"))
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert training._cuda_info(0)["gpu"] == "Test GPU"
    with pytest.raises(RuntimeError, match="device 1"):
        training._cuda_info(1)


def test_candidate_version_rollback_integrity(tmp_path):
    root = tmp_path / "versions"
    version = "v20261106T203000Z-1234abcd"
    folder = root / version
    folder.mkdir(parents=True)
    (folder / "weights.pt").write_bytes(b"test-weights")
    (folder / "model.onnx").write_bytes(b"test-onnx")
    meta = {"version": version, "status": "candidate",
            "artifacts": {name: training.sha256_file(folder / name)
                          for name in ("weights.pt", "model.onnx")}}
    (folder / "manifest.json").write_text(json.dumps(meta), encoding="utf-8")
    assert training.verify_version(root, version)["status"] == "candidate"
    (folder / "model.onnx").write_bytes(b"tampered")
    with pytest.raises(training.DataError, match="modified"):
        training.verify_version(root, version)
    with pytest.raises(training.DataError, match="Invalid model version"):
        training.verify_version(root, "../secret")


def test_training_orchestrates_local_cuda_export_and_keeps_candidate(
        dataset, monkeypatch, tmp_path):
    root, _ = dataset
    versions = tmp_path / "versions"
    weights = tmp_path / "source-seg.pt"
    weights.write_bytes(b"pretrained")
    calls = []

    class Model:
        task = "segment"

        def __init__(self, path):
            self.path = path
            calls.append(("load", path))

        def train(self, **kwargs):
            assert kwargs["device"] == 0
            assert kwargs["data"].endswith("data.yaml")
            assert kwargs["cache"] is False
            assert kwargs["imgsz"] == 640
            saved = Path(kwargs["project"]) / "training" / "weights"
            saved.mkdir(parents=True)
            (saved / "best.pt").write_bytes(b"trained")
            calls.append(("train", kwargs["epochs"]))

        def val(self, **kwargs):
            calls.append(("val", kwargs["device"]))
            return types.SimpleNamespace(
                seg=types.SimpleNamespace(map50=.78, map=.52),
                box=types.SimpleNamespace(map50=.82))

        def export(self, **kwargs):
            assert kwargs["format"] == "onnx" and kwargs["nms"] is False
            assert kwargs["device"] == "cpu"
            path = Path(self.path).with_suffix(".onnx")
            path.write_bytes(b"graph-onnx")
            return str(path)

    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(
        YOLO=Model, __version__="test"))
    monkeypatch.setattr(training, "_cuda_info",
                        lambda device: {"torch": "test", "cuda": "test",
                                        "gpu": "mock Nvidia GPU"})
    monkeypatch.setattr(training, "_smoke_onnx",
                        lambda path, size: {"inputs": ["1x3x640x640"],
                                             "outputs": [[1, 40, 8400],
                                                         [1, 32, 160, 160]]})
    args = argparse.Namespace(
        weights=weights, accept_ultralytics_license=True,
        epochs=2, batch=2, imgsz=640, workers=0, patience=1, seed=42,
        device=0, min_mask_map50=0.25, versions_dir=versions, dataset=root,
        min_train_positive=12, min_val_positive=4,
        min_negative_per_split=1)
    meta = training.train(args, training.validate_dataset(root))
    assert meta["status"] == "candidate"
    assert meta["deployment"] == "not_activated"
    assert training.verify_version(versions, meta["version"])["validation"][
        "mask_map50"] == .78
    assert len(json.loads((versions / "index.json").read_text())[
        "versions"]) == 1
    assert calls[0][0] == "load"
    assert calls[-1][0] == "val"
    assert not list(versions.glob(".staging-*"))
    assert not (versions / ".training.lock").exists()


def test_training_requires_license_acknowledgement(tmp_path):
    args = argparse.Namespace(accept_ultralytics_license=False)
    with pytest.raises(RuntimeError, match="AGPL"):
        training.train(args, {})


def test_dataset_mutation_during_training_rejected(dataset, tmp_path,
                                                    monkeypatch):
    root, _ = dataset
    report = training.validate_dataset(root)
    # Mutated after the first validation, before train() obtains the GPU.
    sample = next((root / "images" / "train").glob("*.jpg"))
    image = cv2.imread(str(sample))
    image[0:10, 0:10] = 0
    cv2.imwrite(str(sample), image)
    assert training.validate_dataset(root)["dataset_sha256"] != report[
        "dataset_sha256"]


def test_onnx_smoke_requires_segmentation_outputs(monkeypatch, tmp_path):
    path = tmp_path / "dummy.onnx"
    path.write_bytes(b"mock-checker-inference")
    validated = []

    class Input:
        name = "images"
        shape = [1, 3, 640, 640]

    class Session:
        def __init__(self, path, providers):
            assert providers == ["CPUExecutionProvider"]

        def get_inputs(self):
            return [Input()]

        def run(self, output_names, inputs):
            assert inputs["images"].shape == (1, 3, 640, 640)
            return [np.zeros((1, 37, 8400), dtype=np.float32),
                    np.zeros((1, 32, 160, 160), dtype=np.float32)]

    monkeypatch.setitem(sys.modules, "onnx", types.SimpleNamespace(
        checker=types.SimpleNamespace(
            check_model=lambda path: validated.append(path))))
    monkeypatch.setitem(sys.modules, "onnxruntime",
                        types.SimpleNamespace(InferenceSession=Session))
    info = training._smoke_onnx(path, 640)
    assert validated == [str(path)]
    assert len(info["outputs"]) == 2
    assert info["outputs"][1] == [1, 32, 160, 160]


def test_onnx_smoke_rejects_non_segment_model(monkeypatch, tmp_path):
    path = tmp_path / "detect.onnx"
    path.write_bytes(b"mock")
    class Input:
        name = "images"
        shape = [1, 3, 640, 640]
    class Session:
        def __init__(self, *args, **kwargs):
            pass
        def get_inputs(self):
            return [Input()]
        def run(self, *args, **kwargs):
            return [np.zeros((1, 5, 8400), dtype=np.float32)]
    monkeypatch.setitem(sys.modules, "onnx", types.SimpleNamespace(
        checker=types.SimpleNamespace(check_model=lambda path: None)))
    monkeypatch.setitem(sys.modules, "onnxruntime",
                        types.SimpleNamespace(InferenceSession=Session))
    with pytest.raises(RuntimeError, match="not a segmentation model"):
        training._smoke_onnx(path, 640)
