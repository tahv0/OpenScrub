"""Live learning telemetry must describe real work without touching GPU tensors."""
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

import learning_session as ls
from scripts import train_plate_seg as trainer
from test_plate_seg_training import dataset  # noqa: F401 -- shared real dataset


PREFIX = "OPENSCRUB_PROGRESS "


def test_stage_timestamps_distinguish_heartbeat_from_real_progress(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ls.time, "time", lambda: now[0])
    job = {"learning": {"source_frame": 19}}
    state = job["learning"]
    ls.update_learning(job, "training", "Training reviewed examples",
                       done=0, total=8, unit="batches")
    assert job["learning"] is state
    assert state["started_at"] == state["last_progress_at"] == 100.0
    now[0] = 105.0
    ls.update_learning(job, "training", "Training reviewed examples",
                       done=0, total=8, unit="batches")
    assert state["started_at"] == state["last_progress_at"] == 100.0
    assert state["updated_at"] == 105.0
    now[0] = 110.0
    ls.update_learning(job, "training", "Completed a batch", done=1)
    assert state["started_at"] == 100.0
    assert state["last_progress_at"] == 110.0
    assert state["total"] == 8 and state["source_frame"] == 19
    now[0] = 115.0
    ls.update_learning(job, "candidate_validation", "Validating the candidate")
    assert state["started_at"] == state["last_progress_at"] == 115.0
    assert state["done"] is None and state["total"] is None
    assert state["unit"] is None


def test_progress_initializes_jobs_without_a_previous_learning_state():
    job = {"learning": None}
    ls.update_learning(job, "queued", "Learning pass queued")
    assert job["learning"]["stage"] == "queued"
    assert job["learning"]["updated_at"] == job["learning"]["started_at"]


def test_real_training_child_streams_progress_and_drains_final_output(tmp_path, monkeypatch):
    script = tmp_path / "training child.py"
    release = tmp_path / "release"
    script.write_text('''import hashlib, json, sys, time
from pathlib import Path
root = Path(sys.argv[sys.argv.index('--versions-dir') + 1])
assert '--progress' in sys.argv
print('ordinary trainer log', flush=True)
sys.stdout.write('OPENSCRUB_PROGRESS {"stage":"training","message":"Epoch 1/2",')
sys.stdout.flush()
time.sleep(.65)
print('"done":3,"total":8,"unit":"batches","epoch":1,"epochs":2,"batch":3,"batches":4}', flush=True)
print('OPENSCRUB_PROGRESS {bad JSON}', flush=True)
print('OPENSCRUB_PROGRESS {"stage":"review","message":"invalid stage"}', flush=True)
print('OPENSCRUB_PROGRESS {"stage":"training","message":"invalid count","done":-1,"total":8}', flush=True)
deadline = time.monotonic() + 10
while not Path(sys.argv[sys.argv.index('--weights') + 1]).exists():
    if time.monotonic() > deadline: raise RuntimeError('test release timeout')
    time.sleep(.01)
folder = root / 'vfixture'
folder.mkdir()
artifacts = {}
for name in ('weights.pt', 'model.onnx'):
    data = b'synthetic artifact; never loaded'
    (folder / name).write_bytes(data)
    artifacts[name] = hashlib.sha256(data).hexdigest()
(folder / 'manifest.json').write_text(json.dumps({'artifacts': artifacts}))
(root / 'index.json').write_text(json.dumps({'versions': [{'version': 'vfixture'}]}))
print('OPENSCRUB_PROGRESS {"stage":"exporting","message":"Exporting ONNX","metrics":{"mask_map50":0.78}}', flush=True)
print('final ordinary log', flush=True)
''', encoding="utf-8")
    monkeypatch.setenv("OPENSCRUB_TRAIN_PYTHON", sys.executable)
    monkeypatch.setattr(ls, "trainer_script", lambda: script)
    job = {"cancel": threading.Event(), "log": [],
           "learning": {"stage": "training", "started_at": 1.0}}
    outcome = []
    failures = []

    def run():
        try:
            outcome.append(ls.run_training(tmp_path / "dataset", tmp_path / "versions",
                                           release, job, {}))
        except Exception as error:
            failures.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        deadline = time.monotonic() + 3
        while job["learning"].get("done") != 3 and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert job["learning"].get("done") == 3, (job, failures)
        assert job["learning"]["stage"] == "training"
        assert job["learning"]["epoch"] == 1 and job["learning"]["batch"] == 3
        assert job["learning"]["started_at"] == 1.0
        assert "ordinary trainer log" in job["log"]
        assert not any(PREFIX in line for line in job["log"])
    finally:
        release.touch()
        worker.join(timeout=12)
    assert not worker.is_alive()
    assert not failures
    assert outcome[0][0].name == "vfixture"
    assert "final ordinary log" in job["log"]
    assert job["learning"]["stage"] == "checking"
    assert job["learning"]["done"] == job["learning"]["total"] == 2
    assert job["learning"]["metrics"]["mask_map50"] == .78
    assert PREFIX in (tmp_path / "training.log").read_text(encoding="utf-8")


class _NoTensorRead:
    def __getattr__(self, name):
        raise AssertionError("Progress must not read or synchronize GPU tensors")

    def __float__(self):
        raise AssertionError("Progress must not convert GPU tensors")


def test_callback_progress_is_throttled_and_counts_completed_batches(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(trainer.time, "monotonic", lambda: now[0])
    output = io.StringIO()
    progress = trainer.TrainingProgress(stream=output)
    state = SimpleNamespace(epoch=0, epochs=2, train_loader=range(20),
                            loss=_NoTensorRead(), tloss=_NoTensorRead())
    progress.on_train_epoch_start(state)
    for i in range(1, 10):
        now[0] = 100.0 + i / 10
        progress.on_train_batch_end(state)
    events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines() if line.startswith(PREFIX)]
    assert len(events) == 1
    assert events[0]["done"] == 0 and events[0]["total"] == 40
    now[0] = 101.0
    progress.on_train_batch_end(state)
    events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines() if line.startswith(PREFIX)]
    assert len(events) == 2
    assert events[-1]["epoch"] == 1 and events[-1]["batch"] == 10
    assert events[-1]["done"] == 10 and events[-1]["total"] == 40
    state.epoch = 1
    now[0] = 102.0
    progress.on_train_epoch_start(state)
    events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines() if line.startswith(PREFIX)]
    assert events[-1]["epoch"] == 2 and events[-1]["batch"] == 0
    assert events[-1]["done"] == 20


def test_training_progress_covers_validation_export_and_existing_checks(dataset, tmp_path, monkeypatch, capsys):
    root, _ = dataset
    weights = tmp_path / "source-seg.pt"
    weights.write_bytes(b"synthetic checkpoint")
    validations = []

    class Model:
        task = "segment"

        def __init__(self, path):
            self.path = Path(path)
            self.callbacks = {}

        def add_callback(self, event, callback):
            self.callbacks[event] = callback

        def train(self, **kwargs):
            state = SimpleNamespace(epoch=0, epochs=2, train_loader=range(2),
                                    loss=_NoTensorRead(), tloss=_NoTensorRead())
            self.callbacks["on_train_epoch_start"](state)
            for _ in range(2):
                self.callbacks["on_train_batch_end"](state)
            self.callbacks["on_train_epoch_end"](state)
            # Early stopping is legitimate: never invent completion of epoch 2.
            folder = Path(kwargs["project"]) / "training" / "weights"
            folder.mkdir(parents=True)
            (folder / "best.pt").write_bytes(b"synthetic trained checkpoint")

        def val(self, **kwargs):
            validations.append(kwargs)
            state = SimpleNamespace(dataloader=range(2))
            self.callbacks["on_val_start"](state)
            for _ in range(2):
                self.callbacks["on_val_batch_end"](state)
            self.callbacks["on_val_end"](state)
            return SimpleNamespace(seg=SimpleNamespace(map50=.78, map=.52),
                                   box=SimpleNamespace(map50=.8))

        def export(self, **kwargs):
            path = self.path.with_suffix(".onnx")
            path.write_bytes(b"synthetic ONNX graph")
            return str(path)

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Model, __version__="fixture"))
    monkeypatch.setattr(trainer, "_cuda_info", lambda device: {"gpu": "fixture"})
    monkeypatch.setattr(trainer, "_smoke_onnx", lambda path, size: {})
    args = SimpleNamespace(
        weights=weights, accept_ultralytics_license=True, epochs=2,
        batch=2, imgsz=640, workers=0, patience=1, seed=42, device=0,
        min_mask_map50=.25, versions_dir=tmp_path / "versions", dataset=root,
        min_train_positive=12, min_val_positive=4, min_negative_per_split=1,
        progress=True)
    result = trainer.train(args, trainer.validate_dataset(root))
    events = [json.loads(line[len(PREFIX):]) for line in capsys.readouterr().out.splitlines() if line.startswith(PREFIX)]
    assert {event["stage"] for event in events} >= {"training", "candidate_validation", "exporting", "checking"}
    training = [event for event in events if event["stage"] == "training" and event.get("unit") == "batches"]
    assert training[-1]["done"] == 2 and training[-1]["total"] == 4
    assert len(validations) == 1
    assert result["validation"]["mask_map50"] == .78
    assert trainer.verify_version(args.versions_dir, result["version"])["status"] == "candidate"
