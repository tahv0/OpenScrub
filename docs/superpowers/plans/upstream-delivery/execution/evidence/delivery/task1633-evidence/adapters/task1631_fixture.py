"""Task-only model seed: keep the prepared model read-only; own the run copy."""
import hashlib
import os
from pathlib import Path
import shutil


def pytest_configure(config):
    cached = Path('/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx')
    expected = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
    assert hashlib.sha256(cached.read_bytes()).hexdigest() == expected
    destination = Path(os.environ['VERIFY_RUN']) / 'models' / cached.name
    shutil.copyfile(cached, destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == expected
