"""CPU-only runtime path regressions; no pretrained models are required."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from infer import cli
from tools.paths import SOURCE_ROOT, runtime_path, runtime_root
from train import process_ckpt


ROOT_ENV = ("RVC_DATA_DIR", "weight_root", "index_root", "outside_index_root", "rmvpe_root")
SPEAKERS = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


class RuntimePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.caller = self.base / "caller"
        self.data = self.caller / "runtime"
        self.data.mkdir(parents=True)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for key in ROOT_ENV:
            os.environ.pop(key, None)
        os.chdir(self.caller)

    def checkpoint(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "weight": {"emb_g.weight": torch.ones(3, 2)},
            "config": [1, 2, 3],
            "speaker_info": SPEAKERS,
        }, path)
        return path

    def test_imports_do_not_change_cwd_environment_or_create_files(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SOURCE_ROOT)
        env["RVC_DATA_DIR"] = "missing-runtime"
        code = """
import os
from pathlib import Path
before = Path.cwd(), dict(os.environ), sorted(Path('.').rglob('*'))
import tools.paths
import infer.cli
import i18n.i18n
import train.process_ckpt
assert before == (Path.cwd(), dict(os.environ), sorted(Path('.').rglob('*')))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=self.caller,
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.caller / "missing-runtime").exists())

    def test_relative_data_dir_is_normalized_before_chdir(self):
        os.environ["RVC_DATA_DIR"] = "runtime"
        os.environ["weight_root"] = "custom/weights"
        os.environ["index_root"] = str(self.base / "external-logs")
        os.environ["outside_index_root"] = "~/external-indices"
        cli.setup_runtime()
        self.assertEqual(Path.cwd(), self.data)
        self.assertEqual(os.environ["RVC_DATA_DIR"], str(self.data))
        self.assertEqual(os.environ["weight_root"], str(self.data / "custom/weights"))
        self.assertEqual(os.environ["index_root"], str(self.base / "external-logs"))
        self.assertEqual(Path(os.environ["outside_index_root"]), Path.home() / "external-indices")
        self.assertEqual(Path(os.environ["rmvpe_root"]), self.data / "assets/rmvpe")
        self.assertFalse((self.data / "custom").exists())

    def test_unset_cli_keeps_project_root_behavior(self):
        cli.setup_runtime()
        self.assertEqual(Path.cwd(), SOURCE_ROOT)
        self.assertEqual(Path(os.environ["weight_root"]), SOURCE_ROOT / "assets/weights")

    def test_relative_inputs_models_and_outputs_use_runtime_not_caller(self):
        os.environ["RVC_DATA_DIR"] = "runtime"
        os.environ["weight_root"] = "models"
        model = self.checkpoint(self.data / "models/model.pth")
        self.checkpoint(self.caller / "models/model.pth")
        self.assertEqual(cli.resolve_model("model.pth"), model)
        direct = self.checkpoint(self.data / "model.pth")
        self.assertEqual(cli.resolve_model("model.pth"), direct)
        self.assertEqual(cli.resolve_model(str(model)), model)
        (self.data / "input.wav").touch()
        (self.caller / "input.wav").touch()
        jobs = cli.collect_jobs("input.wav", "output.wav", None, False)
        self.assertEqual(jobs, [(self.data / "input.wav", self.data / "output.wav", "wav")])

    def test_tilde_paths(self):
        with patch.dict(os.environ, {"HOME": str(self.base), "RVC_DATA_DIR": "~/data"}):
            self.assertEqual(runtime_root(), self.base / "data")
            model = self.checkpoint(self.base / "model.pth")
            self.assertEqual(cli.resolve_model("~/model.pth"), model)
            self.assertEqual(runtime_path("~/absolute.wav"), self.base / "absolute.wav")

    def test_directory_jobs_keep_runtime_relative_layout(self):
        os.environ["RVC_DATA_DIR"] = "runtime"
        (self.data / "inputs/nested").mkdir(parents=True)
        (self.data / "inputs/top.WAV").touch()
        (self.data / "inputs/nested/clip.flac").touch()
        (self.data / "inputs/nested/ignored.txt").touch()
        (self.caller / "inputs").mkdir()
        jobs = cli.collect_jobs("inputs", "outputs", "flac", True)
        self.assertEqual(jobs, [
            (self.data / "inputs/nested/clip.flac", self.data / "outputs/nested/clip.flac", "flac"),
            (self.data / "inputs/top.WAV", self.data / "outputs/top.flac", "flac"),
        ])
        self.assertFalse((self.caller / "outputs").exists())

    def test_locale_uses_source_without_runtime_symlink(self):
        os.chdir(self.data)
        from i18n.i18n import I18nAuto
        self.assertTrue(I18nAuto("en_US").language_map)
        self.assertEqual(I18nAuto("nonexistent").language, "en_US")
        self.assertFalse((self.data / "i18n").exists())

    def test_explicit_and_automatic_index_priorities(self):
        os.environ["RVC_DATA_DIR"] = "runtime"
        cli.setup_runtime()
        logs = self.data / "logs"
        outside = self.data / "assets/indices"
        logs.mkdir()
        outside.mkdir(parents=True)
        log_index = logs / "demo_added_test_spkid1.index"
        outside_index = outside / log_index.name
        log_index.touch()
        outside_index.touch()
        (outside / "demo_trained_test_spkid1.index").touch()
        (outside / "demo_added_test_spkid2.index").touch()
        self.assertEqual(cli.resolve_index(None, "demo_e1_s2.pth", 1, 1), str(outside_index))
        outside_index.unlink()
        self.assertEqual(cli.resolve_index(None, "demo_e1_s2.pth", 1, 1), str(log_index))
        self.assertEqual(cli.resolve_index("logs/demo_trained_test_spkid1.index", "demo.pth", 1, 1), str(log_index))
        self.assertEqual(cli.resolve_index(None, "demo.pth", 1, 0), "")

    def test_cli_list_speakers_direct_script_from_other_cwd(self):
        model = self.checkpoint(self.data / "models/demo.pth")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.update(RVC_DATA_DIR="runtime", weight_root="models", CUDA_VISIBLE_DEVICES="")
        for argument in ("demo.pth", str(model)):
            with self.subTest(model=argument):
                result = subprocess.run(
                    [sys.executable, "-B", str(SOURCE_ROOT / "infer/cli.py"),
                     "--model", argument, "--list-speakers"],
                    cwd=self.caller, env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "1\tAlice\n2\tBob\n")
        self.assertFalse((self.data / "i18n").exists())

    def test_all_four_exports_and_metadata_for_configured_roots(self):
        config = json.loads((SOURCE_ROOT / "configs/v1/40k.json").read_text())
        hps = SimpleNamespace(
            data=SimpleNamespace(**config["data"]),
            model=SimpleNamespace(**config["model"]), speaker_info=SPEAKERS,
        )
        training = self.base / "training"
        training.mkdir()
        training_path = training / "G_1.pth"
        torch.save({"model": {"emb_g.weight": torch.ones(3, 2), "enc_q.test": torch.ones(1)}}, training_path)
        (training / "config.json").write_text(json.dumps({"speaker_info": SPEAKERS}))
        first = self.checkpoint(self.base / "first.pth")
        second = self.checkpoint(self.base / "second.pth")
        cases = [
            ({}, self.caller / "assets/weights"),
            ({"weight_root": "custom/weights"}, self.caller / "custom/weights"),
            ({"RVC_DATA_DIR": "runtime"}, self.data / "assets/weights"),
            ({"RVC_DATA_DIR": str(self.data), "weight_root": "nested/weights"}, self.data / "nested/weights"),
            ({"RVC_DATA_DIR": str(self.data), "weight_root": str(self.base / "absolute/weights")}, self.base / "absolute/weights"),
            ({"RVC_DATA_DIR": str(self.data), "HOME": str(self.base), "weight_root": "~/tilde/weights"}, self.base / "tilde/weights"),
        ]
        for overrides, output in cases:
            with self.subTest(overrides=overrides), patch.dict(os.environ, overrides):
                self.assertEqual(process_ckpt.savee(
                    {"emb_g.weight": torch.ones(3, 2), "enc_q.test": torch.ones(1)},
                    "40k", 1, "saved", 5, "v1", hps,
                ), process_ckpt.i18n("成功"))
                self.assertEqual(process_ckpt.extract_small_model(
                    str(training_path), "extracted", "40k", 1, "", "v1",
                ), process_ckpt.i18n("成功"))
                for name in ("", "renamed.pth"):
                    self.assertEqual(process_ckpt.change_info(str(first), "updated", name), process_ckpt.i18n("成功"))
                self.assertEqual(process_ckpt.merge(
                    str(first), str(second), 0.5, "40k", process_ckpt.i18n("是"), "merged", "merged", "v1",
                ), process_ckpt.i18n("成功"))
                for name in ("saved.pth", "extracted.pth", "first.pth", "renamed.pth", "merged.pth"):
                    checkpoint = torch.load(output / name, map_location="cpu", weights_only=True)
                    self.assertEqual(checkpoint["speaker_info"], SPEAKERS)
                    self.assertNotIn("enc_q.test", checkpoint["weight"])
                self.assertEqual(torch.load(output / "renamed.pth", weights_only=True)["info"], "updated")
                self.assertEqual(torch.load(output / "saved.pth", weights_only=True)["info"], "5epoch")
                self.assertEqual(torch.load(output / "merged.pth", weights_only=True)["config"], [1, 2, 3])
                self.assertEqual(cli.select_speaker(3, SPEAKERS, None), 1)
        self.assertFalse((self.caller / "config.json").exists())


if __name__ == "__main__":
    unittest.main()
