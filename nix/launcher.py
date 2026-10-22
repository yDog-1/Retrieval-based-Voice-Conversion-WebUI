"""Prepare writable state, then exec the packaged application."""

import os
from pathlib import Path
import shutil
import sys


def main():
    source = Path(__file__).resolve().parents[1]
    data = Path(os.environ.get(
        "RVC_DATA_DIR",
        str(Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "rvc"),
    )).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["RVC_DATA_DIR"] = str(data)
    for name in ("webui.py", "realtime_gui.py", "configs", "i18n", "infer", "tools", "train"):
        target = data / name
        expected = source / name
        if target.is_symlink():
            previous = Path(os.readlink(target))
            if previous != expected:
                if not str(previous).startswith("/nix/store/"):
                    raise RuntimeError(f"Not a managed RVC symlink: {target}")
                target.unlink()
                target.symlink_to(expected)
        elif target.exists():
            raise RuntimeError(f"Use a separate RVC_DATA_DIR; code path already exists: {target}")
        else:
            target.symlink_to(expected)
    for name in ("weights", "indices", "hubert_base", "rmvpe", "pretrained", "pretrained_v2", "pymss_weights"):
        (data / "assets" / name).mkdir(parents=True, exist_ok=True)
    for config in (source / "assets/pymss_weights").glob("*.yaml"):
        target = data / "assets/pymss_weights" / config.name
        if not target.exists():
            shutil.copyfile(config, target)
    for name in ("logs", "settings", ".cache/numba"):
        (data / name).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(data / ".cache/numba"))
    os.environ.setdefault("MPLCONFIGDIR", str(data / ".cache/matplotlib"))
    os.environ["PYTHONPATH"] = str(data) + ":" + os.environ.get("PYTHONPATH", "")
    driver = os.environ.get("RVC_DRIVER_LIBRARY_PATH", "/run/opengl-driver/lib")
    os.environ["LD_LIBRARY_PATH"] = driver + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    os.chdir(data)
    entry = sys.argv[1]
    script = {
        "webui": data / "webui.py",
        "realtime": data / "realtime_gui.py",
        "download-models": source / "nix/download_models.py",
        "doctor": source / "nix/doctor.py",
    }[entry]
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[2:]])


if __name__ == "__main__":
    main()
