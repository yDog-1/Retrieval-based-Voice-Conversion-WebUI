"""Download upstream model assets into the selected RVC data directory."""

import argparse
from pathlib import Path
import zipfile

from huggingface_hub import hf_hub_download, snapshot_download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", action="store_true", help="Also download v1/v2 pretrained models and mute samples")
    parser.add_argument("--separation", action="store_true", help="Also download pymss separation weights")
    parser.add_argument("--revision", default="main", help="Hugging Face revision (commit SHA for reproducible downloads)")
    args = parser.parse_args()
    repo = "lj1995/VoiceConversionWebUI"
    assets = Path.cwd() / "assets"
    snapshot_download(repo, revision=args.revision, allow_patterns=["hubert_base/*"], local_dir=assets)
    hf_hub_download(repo, "rmvpe.pt", revision=args.revision, local_dir=assets / "rmvpe")
    if args.training:
        snapshot_download(repo, revision=args.revision, allow_patterns=["pretrained/*", "pretrained_v2/*"], local_dir=assets)
        archive = hf_hub_download(repo, "mute.zip", revision=args.revision, local_dir=".model-downloads")
        with zipfile.ZipFile(archive) as samples:
            samples.extractall("logs")
    if args.separation:
        snapshot_download(repo, revision=args.revision, allow_patterns=["pymss_weights/*"], local_dir=assets)
    print(f"Models downloaded to {assets}")


if __name__ == "__main__":
    main()
