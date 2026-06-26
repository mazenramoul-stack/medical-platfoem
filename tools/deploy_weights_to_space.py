#!/usr/bin/env python3
"""Upload model weights (and the updated Dockerfile) to the Hugging Face Space
so EVERY modality works in the cloud deployment, not just ECG.

Why this exists
---------------
The large weight binaries (*.pt / *.safetensors / *.ckpt) are gitignored
(see .gitignore), so the Space's GitHub clone never receives them. As a result:
    * ECG  works  -> ecglib downloads its own weights, needs no local file
    * Echo fails  -> echonet_seg.pt / echonet_ef.pt missing  (FileNotFoundError)
    * EEG  fails  -> EEG-PREST-16-channels.ckpt / biot_iiic.pt missing
    * MRI  weak   -> falls back to downloading the stock Swin at request time
This script pushes the real weights straight into the Space repo; the Dockerfile
(deploy/huggingface/Dockerfile, `COPY models_weights/`) then bakes them into the
image so nothing has to download at runtime.

Prerequisites
-------------
    pip install -U huggingface_hub
    huggingface-cli login          # OR: set HF_TOKEN to a token with WRITE access
                                   #     to the Space (Settings -> Access Tokens)

Usage (run from the project root)
---------------------------------
    python tools/deploy_weights_to_space.py            # upload + push Dockerfile
    python tools/deploy_weights_to_space.py --dry-run  # list files, upload nothing
    python tools/deploy_weights_to_space.py --space someuser/backend
    python tools/deploy_weights_to_space.py --skip-dockerfile
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_SPACE = "ma-zen-3/backend"
REPO_ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_DIR = REPO_ROOT / "backend" / "models_weights"
DOCKERFILE = REPO_ROOT / "deploy" / "huggingface" / "Dockerfile"

WEIGHT_SUFFIXES = (".pt", ".safetensors", ".ckpt")
ALLOW_PATTERNS = ["*.pt", "*.safetensors", "*.ckpt"]
# Skip the rejected alternative EEG checkpoint (we deploy biot_iiic.pt, not the
# higher-BA full fine-tune that was a rare-class artifact — see VALIDATION.md).
IGNORE_PATTERNS = ["*fullft*"]


def _selected_files() -> list[Path]:
    return sorted(
        p for p in WEIGHTS_DIR.rglob("*")
        if p.is_file()
        and p.suffix in WEIGHT_SUFFIXES
        and "fullft" not in p.name
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--space", default=DEFAULT_SPACE,
                    help=f"HF Space repo id (default: {DEFAULT_SPACE})")
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be uploaded, then exit.")
    ap.add_argument("--skip-dockerfile", action="store_true",
                    help="Upload weights only; do not push the Dockerfile.")
    args = ap.parse_args()

    if not WEIGHTS_DIR.is_dir():
        sys.exit(f"Weights dir not found: {WEIGHTS_DIR}")

    files = _selected_files()
    if not files:
        sys.exit(f"No weight files (*.pt/*.safetensors/*.ckpt) found under {WEIGHTS_DIR}")

    total_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"Weights to upload ({len(files)} files, {total_mb:.0f} MB total):")
    for p in files:
        rel = p.relative_to(WEIGHTS_DIR).as_posix()
        print(f"  models_weights/{rel}  ({p.stat().st_size / 1e6:.0f} MB)")

    if args.dry_run:
        print("\n--dry-run: nothing uploaded.")
        return

    try:
        from huggingface_hub import HfApi, get_token, upload_file, upload_folder
    except ImportError:
        sys.exit("huggingface_hub not installed. Run: pip install -U huggingface_hub")

    token = get_token()
    if not token:
        sys.exit("No HF token found. Run `huggingface-cli login` or set HF_TOKEN "
                 "(token needs WRITE access to the Space).")

    api = HfApi(token=token)
    try:
        who = api.whoami()["name"]
    except Exception as exc:  # noqa: BLE001 - surface auth errors plainly
        sys.exit(f"Could not verify HF login: {exc}")

    print(f"\nLogged in as: {who}")
    print(f"Target Space: {args.space}  (repo_type=space)")
    print("\nUploading weights — this can take several minutes on a slow link...")
    upload_folder(
        repo_id=args.space,
        repo_type="space",
        folder_path=str(WEIGHTS_DIR),
        path_in_repo="models_weights",
        allow_patterns=ALLOW_PATTERNS,
        ignore_patterns=IGNORE_PATTERNS,
        commit_message="Add model weights for all modalities (Echo/EEG/MRI)",
        token=token,
    )
    print("Weights uploaded.")

    if not args.skip_dockerfile:
        if not DOCKERFILE.is_file():
            sys.exit(f"Dockerfile not found: {DOCKERFILE}")
        print("Pushing updated Dockerfile (this triggers the Space rebuild)...")
        upload_file(
            path_or_fileobj=str(DOCKERFILE),
            path_in_repo="Dockerfile",
            repo_id=args.space,
            repo_type="space",
            commit_message="Bake model weights into image (COPY models_weights/)",
            token=token,
        )
        print("Dockerfile pushed.")

    print(f"\nDone. Watch the rebuild here:")
    print(f"    https://huggingface.co/spaces/{args.space}  ->  Logs / App")
    print("When the build finishes, test MRI / Echo / EEG in the app.")


if __name__ == "__main__":
    main()
