"""One-shot setup entry point for every model weight the platform needs.

The first inference request normally triggers ~700 MB of MRI/ECG weight
downloads inside the request thread, and the Echo/EEG modalities need
checkpoints that are NOT auto-downloadable at all. This script makes the
whole story explicit:

    * MRI U-Net        — auto-download via torch.hub (handled here)
    * MRI ViT          — auto-download via HuggingFace (handled here)
    * ECG ecglib       — auto-download via ecglib/torch.hub (handled here)
    * Echo (EchoNet)   — MANUAL: two checkpoints you must place on disk
    * EEG (BIOT/IIIC)  — encoder bundled in repo; head MANUAL (train it)

Usage (from the project root, with the backend venv's Python):
    python tools/download_weights.py                # pre-warm MRI + ECG, then
                                                    # print Echo/EEG instructions
    python tools/download_weights.py --check-only   # report cache status only;
                                                    # never downloads anything

Exit codes:
    --check-only always exits 0 (missing weights are a report, not an error).
    Default mode exits nonzero only if the MRI/ECG warmup itself fails.
"""

from __future__ import annotations

import argparse
import os
import sys

# Force UTF-8 stdout/stderr — keeps parity with the other tools/ scripts on
# Windows consoles that default to cp1252.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, 'backend')

# What model_loader.py actually loads (keep in sync with
# backend/apps/inference/model_loader.py).
UNET_CHECKPOINT = 'unet-e012d006.pt'
UNET_HUB_REPO_DIR = 'mateuszbuda_brain-segmentation-pytorch_master'
VIT_CACHE_DIR = 'models--Devarshi--Brain_Tumor_Classification'
ECG_PATHOLOGIES = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC']

ECHO_DIR = os.path.join(BACKEND_DIR, 'models_weights', 'echonet')
BIOT_DIR = os.path.join(BACKEND_DIR, 'models_weights', 'biot')


# ---- cache-location helpers (no torch / transformers imports) --------------

def torch_hub_dir() -> str:
    """Resolve the torch.hub cache directory without importing torch.

    Mirrors torch.hub.get_dir(): $TORCH_HOME/hub, falling back to
    $XDG_CACHE_HOME/torch/hub, then ~/.cache/torch/hub.

    Returns:
        Absolute path of the torch hub directory (may not exist yet).
    """
    torch_home = os.environ.get('TORCH_HOME')
    if not torch_home:
        xdg = os.environ.get('XDG_CACHE_HOME')
        cache_root = xdg if xdg else os.path.join(os.path.expanduser('~'), '.cache')
        torch_home = os.path.join(cache_root, 'torch')
    return os.path.join(torch_home, 'hub')


def hf_hub_cache_dir() -> str:
    """Resolve the HuggingFace hub cache directory without importing huggingface_hub.

    Mirrors huggingface_hub's resolution: $HF_HUB_CACHE, falling back to
    $HF_HOME/hub, then ~/.cache/huggingface/hub.

    Returns:
        Absolute path of the HF hub cache directory (may not exist yet).
    """
    explicit = os.environ.get('HF_HUB_CACHE')
    if explicit:
        return explicit
    hf_home = os.environ.get('HF_HOME')
    if not hf_home:
        xdg = os.environ.get('XDG_CACHE_HOME')
        cache_root = xdg if xdg else os.path.join(os.path.expanduser('~'), '.cache')
        hf_home = os.path.join(cache_root, 'huggingface')
    return os.path.join(hf_home, 'hub')


def echo_weight_paths() -> list:
    """Return [(label, path)] for the two EchoNet checkpoints.

    Honours the same env-var overrides as model_loader.get_echo_models().
    """
    return [
        ('EchoNet segmentation (echonet_seg.pt)',
         os.environ.get('ECHONET_SEG_WEIGHTS', os.path.join(ECHO_DIR, 'echonet_seg.pt'))),
        ('EchoNet EF regressor (echonet_ef.pt)',
         os.environ.get('ECHONET_EF_WEIGHTS', os.path.join(ECHO_DIR, 'echonet_ef.pt'))),
    ]


def eeg_weight_paths() -> list:
    """Return [(label, path)] for the BIOT encoder + IIIC head checkpoints.

    Honours the same env-var overrides as model_loader.get_eeg_model().
    """
    return [
        ('BIOT pretrained encoder (bundled)',
         os.environ.get('BIOT_ENCODER_WEIGHTS',
                        os.path.join(BIOT_DIR, 'EEG-PREST-16-channels.ckpt'))),
        ('BIOT IIIC 6-class head (biot_iiic.pt)',
         os.environ.get('BIOT_IIIC_WEIGHTS', os.path.join(BIOT_DIR, 'biot_iiic.pt'))),
    ]


# ---- check-only mode --------------------------------------------------------

def _report(label: str, path: str) -> bool:
    """Print one PRESENT/MISSING line for a file or directory path."""
    present = os.path.exists(path)
    print(f"  [{'PRESENT' if present else 'MISSING'}] {label}")
    print(f"            {path}")
    return present


def check_only() -> int:
    """Report weight/cache status for every modality. Never downloads.

    Pure filesystem existence checks — no torch model is loaded, so this is
    safe and fast even on a machine with nothing cached yet.

    Returns:
        Always 0 (missing weights are informational, not an error).
    """
    hub = torch_hub_dir()
    checkpoints = os.path.join(hub, 'checkpoints')
    hf = hf_hub_cache_dir()

    print('=' * 72)
    print('WEIGHT / CACHE STATUS (--check-only: nothing will be downloaded)')
    print('=' * 72)

    print('\nMRI — auto-downloaded on first use')
    unet_ok = _report('U-Net checkpoint (torch.hub)',
                      os.path.join(checkpoints, UNET_CHECKPOINT))
    unet_repo_ok = _report('U-Net hub repo snapshot',
                           os.path.join(hub, UNET_HUB_REPO_DIR))
    vit_ok = _report('ViT classifier (HuggingFace cache)',
                     os.path.join(hf, VIT_CACHE_DIR))

    print('\nECG — auto-downloaded on first use (ecglib -> torch.hub cache)')
    ecg_found = 0
    for p in ECG_PATHOLOGIES:
        if _report(f'DenseNet-1D-121 [{p}]',
                   os.path.join(checkpoints, f'12_leads_densenet1d121_{p}.pt')):
            ecg_found += 1

    print('\nEcho — NOT auto-downloaded (manual step, see default mode)')
    echo_ok = all(_report(label, path) for label, path in echo_weight_paths())

    print('\nEEG — encoder bundled; IIIC head NOT bundled (manual step)')
    eeg_ok = all(_report(label, path) for label, path in eeg_weight_paths())

    print('\n' + '=' * 72)
    print('SUMMARY')
    print('=' * 72)
    print(f"  MRI  : {'ready' if (unet_ok and unet_repo_ok and vit_ok) else 'will download on first run (or run this script without --check-only)'}")
    print(f"  ECG  : {ecg_found}/{len(ECG_PATHOLOGIES)} pathology checkpoints cached")
    print(f"  Echo : {'ready' if echo_ok else 'MISSING — manual download required (run without --check-only for instructions)'}")
    print(f"  EEG  : {'ready' if eeg_ok else 'MISSING — train the IIIC head (run without --check-only for instructions)'}")
    return 0


# ---- default (download) mode -------------------------------------------------

def _print_manual_instructions() -> None:
    """Print the two manual setup steps (EchoNet checkpoints, EEG IIIC head)."""
    echo_missing = [(l, p) for l, p in echo_weight_paths() if not os.path.exists(p)]
    eeg_missing = [(l, p) for l, p in eeg_weight_paths() if not os.path.exists(p)]

    print('\n' + '=' * 72)
    print('MANUAL STEP 1/2 — EchoNet-Dynamic checkpoints (Echo modality)')
    print('=' * 72)
    if not echo_missing:
        print('  Already present — nothing to do.')
    else:
        print('  EchoNet weights are NOT auto-downloaded. Obtain the pretrained')
        print('  EchoNet-Dynamic checkpoints from:')
        print('      https://echonet.github.io/dynamic/')
        print('      https://github.com/echonet/dynamic')
        print('  and place them at:')
        for _, p in echo_weight_paths():
            print(f'      {p}')
        print('  (or point ECHONET_SEG_WEIGHTS / ECHONET_EF_WEIGHTS env vars at them).')

    print('\n' + '=' * 72)
    print('MANUAL STEP 2/2 — EEG IIIC classification head (EEG modality)')
    print('=' * 72)
    if not eeg_missing:
        print('  Already present — nothing to do.')
    else:
        print('  BIOT only releases the pretrained encoder (bundled in this repo).')
        print('  The 6-class IIIC head must be fine-tuned locally:')
        print('      python tools/train_eeg_head.py')
        print('  using the Kaggle HMS dataset:')
        print('      https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification')
        iiic_path = eeg_weight_paths()[1][1]
        print('  The trained head is saved to:')
        print(f'      {iiic_path}')
        print('  (or point BIOT_IIIC_WEIGHTS at an existing fine-tuned checkpoint).')


def download() -> int:
    """Pre-warm the auto-downloadable models, then print the manual steps.

    Calls ModelLoader.warmup(), which force-loads the MRI U-Net, MRI ViT and
    ECG ecglib models — downloading ~700 MB into the local caches on a fresh
    machine, or completing in seconds when everything is already cached.
    Echo and EEG weights cannot be auto-downloaded; clear instructions for
    those two manual steps are printed afterwards.

    Returns:
        0 on success, 1 if the warmup raised.
    """
    # Make the backend package importable (same bootstrap as
    # backend/apps/inference/test_pipelines.py).
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)

    print('=' * 72)
    print('PRE-WARMING AUTO-DOWNLOADABLE MODELS (MRI + ECG, ~700 MB first run)')
    print('=' * 72)
    try:
        from apps.inference.model_loader import ModelLoader
        ModelLoader().warmup()
    except Exception as e:  # noqa: BLE001 — setup script, report and exit nonzero
        print(f'\nWARMUP FAILED: {type(e).__name__}: {e}')
        print('Check that you are using the backend venv Python and that')
        print('backend/requirements.txt (the heavy ML stack) is installed.')
        return 1
    print('\nMRI + ECG models are loaded and cached.')
    print('Caches: ~/.cache/torch/hub/ (U-Net, ecglib) and ~/.cache/huggingface/ (ViT).')

    _print_manual_instructions()

    print('\n' + '=' * 72)
    print('Done. Re-run with --check-only to see per-file status at any time.')
    print('=' * 72)
    return 0


def main() -> int:
    """Parse CLI args and dispatch to check-only or download mode."""
    parser = argparse.ArgumentParser(
        description='Set up model weights for all four modalities '
                    '(MRI, ECG, Echo, EEG).')
    parser.add_argument(
        '--check-only', action='store_true',
        help='Only report which weights/caches are present. Downloads nothing, '
             'loads no models, always exits 0.')
    args = parser.parse_args()
    return check_only() if args.check_only else download()


if __name__ == '__main__':
    sys.exit(main())
