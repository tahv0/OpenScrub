"""No-GPU, no-Docker regression tests for CUDA dependency audit and layer plan."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "docker" / "audit_cuda_image.py"
SPEC = importlib.util.spec_from_file_location("audit_cuda_image", MODULE)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class CudaAuditTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_components_categorize_installed_packages_without_user_data(self):
        self.put("usr/local/lib/python3.10/dist-packages/paddle/libpaddle.so", b"a" * 111)
        self.put("opt/openscrub-training/lib/python3.10/site-packages/torch/libtorch.so", b"b" * 222)
        self.put("opt/opencv/lib/libopencv_core.so", b"c" * 333)
        self.put("root/.openscrub/models/detector.onnx", b"d" * 444)
        self.put("root/.local/share/OpenScrub/jobs/private.mkv", b"SECRET" * 100)
        first = audit_module.audit(self.root)
        second = audit_module.audit(self.root)
        self.assertEqual(first, second, "Report should be deterministic")
        components = {c["category"]: c for c in first["components"]}
        self.assertEqual(components["inference-python"]["bytes"], 111)
        self.assertEqual(components["training-python"]["bytes"], 222)
        self.assertEqual(components["opencv-cuda"]["bytes"], 333)
        self.assertEqual(components["prefetched-models"]["bytes"], 444)
        self.assertEqual(first["total_scanned_bytes"], 1110)
        self.assertNotIn("private", json.dumps(first))
        self.assertNotIn("SECRET", json.dumps(first))
        self.assertEqual(components["inference-python"]["largest"][0]["name"], "paddle")

    def test_symlinks_are_not_followed_or_double_counted(self):
        source = self.put("usr/local/cuda-12.6/lib64/libcuda.so", b"C" * 28)
        (self.root / "usr/local/cuda").symlink_to(source.parent, target_is_directory=True)
        training = self.root / "opt/openscrub-training/lib/python3.10/site-packages"
        training.mkdir(parents=True)
        (training / "external").symlink_to(source.parent, target_is_directory=True)
        result = audit_module.audit(self.root)
        self.assertEqual(result["total_scanned_bytes"], 28)
        self.assertEqual(result["total_scanned_files"], 1)

    def test_candidates_are_not_declared_duplicates_without_hash_proof(self):
        source = self.put("usr/local/lib/python3.10/dist-packages/first/libsame.so", b"ABCD")
        other = self.put("opt/openscrub-training/lib/python3.10/site-packages/second/libsame.so", b"WXYZ")
        candidates = audit_module.audit(self.root)
        self.assertEqual(len(candidates["possible_duplicate_libraries"]), 1)
        self.assertEqual(candidates["verified_identical_libraries"], [])
        verified = audit_module.audit(self.root, verify_duplicates=True)
        self.assertEqual(verified["verified_identical_libraries"], [])
        other.write_bytes(source.read_bytes())
        verified = audit_module.audit(self.root, verify_duplicates=True)
        self.assertEqual(len(verified["verified_identical_libraries"]), 1)
        self.assertEqual(verified["verified_identical_libraries"][0]["bytes_each"], 4)
        limited = audit_module.audit(self.root, verify_duplicates=True, max_hash_bytes=2)
        self.assertEqual(len(limited["not_hashed_due_to_size"]), 1)

    def test_audit_is_strictly_read_only(self):
        source = self.put("opt/opencv/lib/libopencv_dnn.so", b"unchanged")
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        audit_module.audit(self.root, verify_duplicates=True)
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)


class SharedLayerPlanTests(unittest.TestCase):
    def test_stage_tree_shares_core_without_embedding_trainer_in_inference(self):
        plan = json.loads((ROOT / "docker/cuda-shared-layers.json").read_text("utf-8"))
        nodes = {n["id"]: n for n in plan["target"]}
        self.assertEqual(len(nodes), len(plan["target"]))
        self.assertIsNone(nodes["cuda-core"]["parent"])
        self.assertEqual(nodes["opencv-cuda"]["parent"], "cuda-core")
        self.assertEqual(nodes["inference-deps"]["parent"], "opencv-cuda")
        self.assertEqual(nodes["scan-app"]["parent"], "inference-deps")
        self.assertEqual(nodes["training-deps"]["parent"], "cuda-core")
        self.assertEqual(nodes["trainer-worker"]["parent"], "training-deps")
        self.assertIn("PyTorch", nodes["scan-app"]["excludes"] + nodes["inference-deps"]["excludes"])
        self.assertIn("PaddlePaddle GPU", nodes["training-deps"]["excludes"])
        self.assertEqual(plan["current"]["windows_retained_dependency_image"],
                         "openscrub-cuda-deps:local")

    def test_plan_agrees_with_current_cuda_base(self):
        plan = json.loads((ROOT / "docker/cuda-shared-layers.json").read_text("utf-8"))
        dockerfile = (ROOT / "Dockerfile.cuda").read_text("utf-8")
        opencv = (ROOT / "docker/Dockerfile.opencv-cuda").read_text("utf-8")
        self.assertIn("FROM " + plan["current"]["gpu_base"] + " AS cuda_deps", dockerfile)
        self.assertIn("FROM " + plan["target"][0]["from"], opencv)
        self.assertIn(plan["current"]["training_python"], dockerfile)


if __name__ == "__main__":
    unittest.main()
