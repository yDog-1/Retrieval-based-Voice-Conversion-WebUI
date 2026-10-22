"""Check packaged dependencies, and optionally the host GPU and desktop."""

import argparse
import importlib
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-cuda", action="store_true", help="Skip host GPU checks (e.g. Nix sandbox)")
    parser.add_argument("--gui", action="store_true", help="Also open a Tk window and enumerate audio devices")
    args = parser.parse_args()
    for module in (
        "torch", "torchaudio", "numpy", "scipy", "faiss", "librosa", "av",
        "cv2", "parselmouth", "soundfile", "sounddevice", "tkinter", "FreeSimpleGUI",
        "transformers", "torchfcpe", "gradio", "onnxruntime", "pymss", "tensorboard",
    ):
        importlib.import_module(module)
        print(f"OK: {module}", flush=True)
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
