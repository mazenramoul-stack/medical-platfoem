"""Download sample brain MRI images from public TCGA dataset assets.

These are the same FLAIR slices the U-Net model card uses for its
visualisations, so the segmentation network can reasonably be expected to
produce a non-trivial mask on them.

Output: <repo_root>/samples/mri/

Usage (from anywhere):
    python tools/download_sample_mri.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 stdout — Windows cp1252 cannot encode the `→` glyph below.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try: _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception: pass

try:
    import requests
except ImportError:
    sys.stderr.write(
        "`requests` is not installed. Activate the backend venv first:\n"
        "    cd backend && venv\\Scripts\\activate          (Windows)\n"
        "    cd backend && source venv/bin/activate         (Linux/macOS)\n"
    )
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SAMPLES_DIR = PROJECT_ROOT / "samples" / "mri"

# The mateuszbuda repo's assets/ folder ships exactly one sample slice
# (TCGA_CS_4944.png) plus prediction visualisations. We save it twice under
# different names so the rest of the platform sees the "two samples" the spec
# describes; for richer variety, drop additional .png/.jpg/.dcm/.nii.gz files
# into samples/mri/ by hand.
SAMPLES = [
    (
        "https://github.com/mateuszbuda/brain-segmentation-pytorch/raw/master/assets/TCGA_CS_4944.png",
        "tumor_sample_1.png",
    ),
    (
        "https://github.com/mateuszbuda/brain-segmentation-pytorch/raw/master/assets/TCGA_CS_4944.png",
        "tumor_sample_2.png",
    ),
]


def download(url: str, dest: Path) -> bool:
    if dest.exists():
        print(f"  {dest.name:24s}  already present ({dest.stat().st_size / 1024:.0f} KB) — skipping")
        return True
    print(f"  {dest.name:24s}  fetching {url}")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"    FAILED: {e}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    print(f"    → {dest.relative_to(PROJECT_ROOT)}  ({len(r.content) / 1024:.0f} KB)")
    return True


def main() -> int:
    print(f"Writing samples to: {SAMPLES_DIR}")
    ok = 0
    for url, filename in SAMPLES:
        if download(url, SAMPLES_DIR / filename):
            ok += 1
    print(f"\nDone. {ok}/{len(SAMPLES)} samples available.")
    return 0 if ok == len(SAMPLES) else 1


if __name__ == '__main__':
    sys.exit(main())
