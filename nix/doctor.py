"""Check packaged dependencies, and optionally the host GPU and desktop."""

import argparse
import importlib
from importlib import resources
from pathlib import Path
import subprocess
import sys


def assert_vendored_origins(tools):
    """Reject cached or transitively imported copies from outside packaged tools."""
    tools = Path(tools).resolve()
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] not in ("pymss", "pymss_core") or module is None:
            continue
        # pymss.modules intentionally aliases several pymss_core.modules.
        packages = (tools / "pymss", tools / "pymss_core")
        origin = getattr(module, "__file__", None)
        locations = tuple(getattr(module, "__path__", ()))
        # Resource directories are PEP 420 namespace packages (no __init__.py).
        if (origin is None and not locations) or (
            origin is not None and not any(Path(origin).resolve().is_relative_to(path) for path in packages)
        ):
            raise RuntimeError(f"Wrong vendored origin for {name}: {origin}; expected {packages}")
        for location in locations:
            if not any(Path(location).resolve().is_relative_to(path) for path in packages):
                raise RuntimeError(f"Wrong vendored package path for {name}: {location}")


def check_vendored_pymss():
    """Exercise the WebUI's vendored API and resources without initializing Config."""
    tools = Path(__file__).resolve().parents[1] / "tools"
    # Use the installed code location, never the caller's writable data directory.
    sys.path.insert(0, str(tools))
    assert_vendored_origins(tools)
    modules = {}
    for name in (
        "pymss", "pymss_core", "pymss.model_registry",
        "pymss.resources", "pymss_core.resources.vr_modelparams",
        "pymss.modules.vocal_remover.vr_separator",
        "pymss_core.modules.vocal_remover.uvr_lib_v5.vr_network.model_param_init",
    ):
        module = importlib.import_module(name)
        assert_vendored_origins(tools)
        expected = tools.joinpath(*name.split("."))
        if expected.is_dir() and not (expected / "__init__.py").exists():
            actual = [Path(path).resolve() for path in module.__path__]
            if actual != [expected.resolve()]:
                raise RuntimeError(f"Wrong vendored namespace origin for {name}: {actual}; expected {expected}")
            origin = expected
        else:
            expected = expected / "__init__.py" if expected.is_dir() else expected.with_suffix(".py")
            origin = getattr(module, "__file__", None)
            if origin is None or Path(origin).resolve() != expected.resolve():
                raise RuntimeError(f"Wrong vendored origin for {name}: {origin}; expected {expected}")
        modules[name] = module
        print(f"OK: {name} from {origin}", flush=True)

    registry = modules["pymss.model_registry"]
    registry.load_model_catalog.cache_clear()
    models = registry.list_models()
    if not models or not all(isinstance(model, registry.ModelEntry) for model in models):
        raise RuntimeError("Vendored model_catalog.json did not load model entries")
    print(f"OK: model_catalog.json ({len(models)} models)", flush=True)

    vr = modules["pymss.modules.vocal_remover.vr_separator"]
    parameter_api = modules["pymss_core.modules.vocal_remover.uvr_lib_v5.vr_network.model_param_init"]
    if vr.ModelParameters is not parameter_api.ModelParameters:
        raise RuntimeError("VR separator is not using vendored core ModelParameters")
    expected_resources = tools / "pymss_core/resources/vr_modelparams"
    paths = sorted(vr.VR_PARAMS_DIR.iterdir(), key=lambda path: path.name)
    paths = [path for path in paths if path.name.endswith(".json")]
    if not paths:
        raise RuntimeError("No vendored VR modelparams resources found")
    for path in paths:
        # Use the same lookup as VRSeparator; namespace roots are Traversables,
        # not filesystem paths, so validate the resolved individual resources.
        with resources.as_file(vr.VR_PARAMS_DIR / path.name) as config:
            if config.resolve() != (expected_resources / path.name).resolve():
                raise RuntimeError(f"Wrong VR resource origin: {config}")
            params = vr.ModelParameters(str(config)).param
        if not params.get("band") or not all(isinstance(key, int) for key in params["band"]):
            raise RuntimeError(f"Invalid VR modelparams bands: {path}")
        if not params.get("bins"):
            raise RuntimeError(f"Invalid VR modelparams bins: {path}")
    print(f"OK: VR modelparams ({len(paths)} resources) from {expected_resources}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-cuda", action="store_true", help="Skip host GPU checks (e.g. Nix sandbox)")
    parser.add_argument("--gui", action="store_true", help="Also open a Tk window and enumerate audio devices")
    args = parser.parse_args()
    for module in (
        "torch", "torchaudio", "numpy", "scipy", "faiss", "librosa", "av",
        "cv2", "parselmouth", "soundfile", "sounddevice", "tkinter", "FreeSimpleGUI",
        "transformers", "torchfcpe", "gradio", "onnxruntime", "tensorboard",
    ):
        importlib.import_module(module)
        print(f"OK: {module}", flush=True)
    check_vendored_pymss()
    import numpy as np
    import soundfile as sf
    import torch
    from infer.hubert import HUBERT_MODEL_PATH

    assert HUBERT_MODEL_PATH == Path.cwd() / "assets/hubert_base"
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        audio = Path(directory) / "silence.wav"
        sf.write(audio, np.zeros(1600, dtype=np.float32), 16000)
        assert sf.read(audio)[1] == 16000
        subprocess.run(["ffprobe", "-v", "error", str(audio)], check=True)
    assert torch.version.cuda == "11.8", torch.version.cuda
    if not args.no_cuda:
        import ctypes
        import onnxruntime

        ctypes.CDLL(str(Path(onnxruntime.__file__).parent / "capi/libonnxruntime_providers_cuda.so"))
        assert "CUDAExecutionProvider" in onnxruntime.get_available_providers()
        assert torch.cuda.is_available(), "NVIDIA driver / CUDA is unavailable"
        x = torch.ones((32, 32), device="cuda")
        assert (x @ x).sum().item() == 32768
        conv = torch.nn.Conv1d(1, 2, 3).cuda()
        assert conv(torch.ones((1, 1, 16), device="cuda")).shape == (1, 2, 14)
        torch.cuda.synchronize()
        print(f"CUDA OK: {torch.cuda.get_device_name(0)} / {torch.__version__}")
    if args.gui:
        import tkinter
        import sounddevice
        window = tkinter.Tk()
        window.update()
        window.destroy()
        print(sounddevice.query_devices())
    print(f"Runtime OK: {Path.cwd()}")


if __name__ == "__main__":
    main()
