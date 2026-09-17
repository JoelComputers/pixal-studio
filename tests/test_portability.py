import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pixal_pipeline import build_graph
from settings import load_settings
import doctor


class PortabilityTests(unittest.TestCase):
    def test_matches_graph_from_successful_detailed_generation(self):
        expected = json.loads((ROOT / "tests/fixtures/completed_detail_graph.json").read_text())
        self.assertEqual(build_graph("reference.png", "detail", 42, "regression"), expected)

    def test_graphs_do_not_share_mutable_state(self):
        first = build_graph("a.png", "detail", 10, "first", {"vision": "custom/vision.safetensors"})
        first["51"]["inputs"]["smooth_iters"] = 999
        second = build_graph("b.png", "preview", 20, "second")
        self.assertEqual(second["51"]["inputs"]["smooth_iters"], 20)
        self.assertEqual(second["4"]["inputs"]["clip_name"], "dino_v3_L_naf_fp32.safetensors")
        self.assertEqual(second["31"]["inputs"]["seed"], 34)
        self.assertEqual(second["61"]["inputs"]["mesh"], ["54", 0])

    def test_rejects_output_traversal(self):
        with self.assertRaises(ValueError):
            build_graph("a.png", job_id="../../escape")

    def test_config_paths_relative_to_config_not_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text(json.dumps({"output_dir": "results", "models": {"vision": "alias/vision.safetensors"}}))
            settings = load_settings(config, {"PIXAL_COMFY_URL": "http://localhost:1234/"})
            self.assertEqual(settings["output_dir"], Path(folder).resolve() / "results")
            self.assertEqual(settings["comfy_url"], "http://localhost:1234")
            self.assertEqual(settings["models"]["vision"], "alias/vision.safetensors")

    def test_missing_explicit_config_fails_instead_of_silent_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                load_settings(Path(folder) / "missing.json", {})

    def test_pipeline_import_has_no_gpu_or_network_dependencies(self):
        result = subprocess.run([sys.executable, "-c",
            "import sys; from pixal_pipeline import build_graph; build_graph('a.png'); "
            "assert not any(x in sys.modules for x in ('torch','aiohttp','urllib.request'))"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hash_verifier_detects_same_size_corruption(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifests").mkdir()
            (root / "models/vae").mkdir(parents=True)
            model = root / "models/vae/test.bin"
            model.write_bytes(b"bad!")
            (root / "manifests/models.json").write_text(json.dumps({"models": [{
                "role": "shape_vae", "path": "vae/test.bin", "bytes": 4,
                "sha256": hashlib.sha256(b"good").hexdigest()}]}))
            with patch.object(doctor, "ROOT", root):
                errors, _ = doctor.check_models({"models_dir": root / "models", "models": {"shape_vae": "test.bin"}}, True)
            self.assertIn("SHA256 mismatch", errors[0])


class PortableHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name)
        (root / "output").mkdir()
        (root / "data/jobs").mkdir(parents=True)
        config = root / "config.json"
        config.write_text(json.dumps({"comfy_url": "http://127.0.0.1:1", "data_dir": "data", "output_dir": "output"}))
        (root / "output/example.glb").write_bytes(b"glTF-test-output")
        (root / "data/jobs/fixture.json").write_text(json.dumps({"id": "fixture", "name": "Fixture", "created": "2026-09-17", "status": "completed", "files": {"model": {"path": str(root / "output/example.glb"), "name": "example.glb", "bytes": 16}}}))
        env = os.environ | {"PIXAL_CONFIG": str(config)}
        for variable in ("PIXAL_OUTPUT_DIR", "PIXAL_DATA_DIR", "PIXAL_COMFY_URL"):
            env.pop(variable, None)
        cls.process = subprocess.Popen([sys.executable, "-u", str(ROOT / "server.py"), "--port", "0"],
            cwd=cls.folder.name, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = cls.process.stdout.readline().strip()
        if not line.startswith("Pixal Studio: "):
            raise RuntimeError("Server did not start: " + cls.process.stderr.read())
        cls.url = line.split(": ", 1)[1]

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=10)
        cls.folder.cleanup()

    def test_history_and_output_survive_relocation(self):
        with urllib.request.urlopen(self.url + "/api/jobs", timeout=5) as response:
            jobs = json.load(response)["jobs"]
        self.assertEqual(jobs[0]["id"], "fixture")
        self.assertNotIn("path", jobs[0]["files"]["model"])
        with urllib.request.urlopen(self.url + "/file/fixture/model?download=1", timeout=5) as response:
            self.assertEqual(response.read(), b"glTF-test-output")
            self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_local_viewer_assets(self):
        for route in ("/", "/app.js", "/vendor/build/three.module.js",
                      "/vendor/examples/jsm/loaders/GLTFLoader.js",
                      "/vendor/examples/jsm/utils/BufferGeometryUtils.js"):
            with urllib.request.urlopen(self.url + route, timeout=5) as response:
                self.assertGreater(len(response.read()), 100)

    def test_unknown_job_cannot_be_cancelled(self):
        request = urllib.request.Request(self.url + "/api/jobs/not-owned/cancel", data=b"")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 404)

    def test_invalid_image_rejected_before_backend_access(self):
        request = urllib.request.Request(self.url + "/api/jobs", data=b"invalid image")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
