"""Singleton loader that holds all pre-trained model instances in memory.

Design contract:
    * One process-wide instance (Python singleton via __new__).
    * Lazy: a model is only downloaded/loaded the first time it is asked for.
    * Cached: subsequent calls return the same instance (no re-download).
    * Device-aware: CUDA used automatically if available, else CPU.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ModelLoader:
    """Process-wide singleton that owns the pre-trained MRI and ECG models."""

    _instance: "ModelLoader | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._unet = None
        self._vit = None
        self._vit_processor = None
        self._ecg_models = None
        self._echo_seg = None
        self._echo_ef = None
        self._eeg = None
        self._device = None
        self._initialized = True

    # ---- device --------------------------------------------------------

    def get_device(self) -> str:
        """Return 'cuda' if a GPU is visible, else 'cpu'. Resolved once and cached."""
        if self._device is None:
            import torch
            self._device = 'cuda' if torch.cuda.is_available() else 'cpu'
            logger.info("Inference device: %s", self._device)
        return self._device

    # ---- MRI segmentation (U-Net) --------------------------------------

    def get_mri_segmentation_model(self):
        """Return the U-Net trained on TCGA-LGG for FLAIR-MRI tumor segmentation.

        Source: PyTorch Hub `mateuszbuda/brain-segmentation-pytorch`.
        Architecture: U-Net, ~7.7M params, 3 in-channels, 1 out-channel.
        First call downloads ~30MB; cached thereafter.
        """
        if self._unet is None:
            print("Loading U-Net model (first time — downloading weights ~30MB)...")
            logger.info("Loading U-Net from torch.hub: mateuszbuda/brain-segmentation-pytorch")
            import torch
            self._unet = torch.hub.load(
                'mateuszbuda/brain-segmentation-pytorch',
                'unet',
                in_channels=3,
                out_channels=1,
                init_features=32,
                pretrained=True,
                trust_repo=True,
            )
            self._unet.eval()
            self._unet.to(self.get_device())
            logger.info("U-Net loaded and moved to %s", self._device)
        return self._unet

    # ---- MRI classification (ViT) --------------------------------------

    def get_mri_classifier(self):
        """Return (processor, model) for the 4-class brain-tumor classifier.

        Source: HuggingFace `Devarshi/Brain_Tumor_Classification`.
        Architecture: Swin Transformer, Swin-Tiny config (embed_dim 96,
        depths [2,2,6,2], window 7, patch 4; ~28M params) — NOT a ViT-B/16,
        despite the historical `vit_brain_tumor` directory name. The classes and
        their integer ids — glioma_tumor=0, meningioma_tumor=1, no_tumor=2,
        pituitary_tumor=3 — come straight from the model config; the MRI
        pipeline reads `model.config.id2label` for label names, so any
        replacement MUST preserve that mapping.
        First call downloads ~110MB; cached thereafter.

        A locally fine-tuned classifier takes precedence over the hub model
        when present (mirrors the EchoNet weights pattern). Point at a
        `transformers` `save_pretrained` directory via env var, else it
        defaults to backend/models_weights/vit_brain_tumor/:
            VIT_BRAIN_TUMOR_WEIGHTS  (default: models_weights/vit_brain_tumor/)
        The directory is used only when it exists and contains a `config.json`.
        If it also ships an image-processor config (`preprocessor_config.json`)
        that processor is loaded too; otherwise the hub processor is kept.
        When no such directory is present, behaviour is byte-identical to
        loading the hub model directly.
        """
        if self._vit is None:
            import os
            from transformers import AutoImageProcessor, AutoModelForImageClassification
            name = "Devarshi/Brain_Tumor_Classification"

            here = os.path.dirname(os.path.abspath(__file__))
            default_dir = os.path.abspath(
                os.path.join(here, '..', '..', 'models_weights', 'vit_brain_tumor'))
            local_dir = os.environ.get('VIT_BRAIN_TUMOR_WEIGHTS', default_dir)
            # Require BOTH the config AND an actual weights file: the repo ships
            # config.json/preprocessor_config.json as sidecars but gitignores the
            # large weights (*.bin/*.safetensors). On a deploy without the weights
            # the dir has a config but no model — fall back to the hub model
            # instead of crashing in from_pretrained.
            _weight_files = (
                'pytorch_model.bin', 'model.safetensors',
                'pytorch_model.bin.index.json', 'model.safetensors.index.json',
            )
            use_local = (
                os.path.isdir(local_dir)
                and os.path.exists(os.path.join(local_dir, 'config.json'))
                and any(os.path.exists(os.path.join(local_dir, w)) for w in _weight_files)
            )

            if use_local:
                print(f"Loading fine-tuned Swin classifier from local dir: {local_dir}")
                logger.info("Loading fine-tuned Swin classifier from local dir: %s", local_dir)
                self._vit = AutoModelForImageClassification.from_pretrained(local_dir)
                if os.path.exists(os.path.join(local_dir, 'preprocessor_config.json')):
                    self._vit_processor = AutoImageProcessor.from_pretrained(local_dir)
                    logger.info("Using image processor from local dir: %s", local_dir)
                else:
                    self._vit_processor = AutoImageProcessor.from_pretrained(name)
                    logger.info(
                        "Local dir has no preprocessor_config.json; using hub processor: %s",
                        name)
            else:
                print("Loading Swin classifier (first time — downloading weights ~110MB)...")
                logger.info("Loading Swin classifier from HuggingFace: Devarshi/Brain_Tumor_Classification")
                logger.warning(
                    "MRI classifier: fine-tuned weights NOT found at %s — falling "
                    "back to the STOCK hub model (~80.4%% accuracy). The headline "
                    "95.4%% figure requires the fine-tuned checkpoints; see "
                    "Colab PFE/README.md / tools/download_weights.py.", local_dir)
                print("WARNING: using STOCK Swin classifier (~80.4%); fine-tuned 95.4% weights absent.")
                self._vit_processor = AutoImageProcessor.from_pretrained(name)
                self._vit = AutoModelForImageClassification.from_pretrained(name)

            self._vit.eval()
            self._vit.to(self.get_device())
            logger.info("ViT loaded and moved to %s", self._device)
        return self._vit_processor, self._vit

    # ---- ECG pathology classifiers (ecglib DenseNet-1D) ----------------

    def get_ecg_models(self) -> dict:
        """Return a dict {pathology_code: model} of pre-trained DenseNet-1D-121s.

        Source: ecglib (ISPRAS), pretrained on 500,000+ ECG records.
        Architecture: DenseNet-1D-121, ~8M params, 12-lead input.
        Each pathology has its own binary classifier; we load all that succeed.
        Failures (e.g. missing weights for a code) log a warning and continue.

        Locally fine-tuned per-pathology weights take precedence over the stock
        ecglib weights when present (mirrors the ViT/EchoNet local-weights
        pattern). After a model is built from the ecglib pretrained checkpoint,
        the loader looks for a plain ``state_dict`` saved as ``<PATHOLOGY>.pt``
        (e.g. ``AFIB.pt``) in ``ECG_FINETUNED_DIR`` (env var, default
        ``backend/models_weights/ecg_finetuned/``) and, if found, loads it over
        the model. Checkpoints are produced by
        ``Colab PFE/colab_ecg_finetune.ipynb`` (only saved when they beat the
        baseline on PTB-XL fold 10). A missing/empty directory means behaviour
        is byte-identical to stock ecglib; a corrupt fine-tuned file logs a
        warning and keeps the pretrained weights for that pathology.
        """
        if self._ecg_models is None:
            print("Loading ecglib pathology models (first time — downloading weights)...")
            logger.info("Loading ecglib DenseNet-1D-121 pathology classifiers")
            import os
            import torch
            from ecglib.models import create_model
            # ecglib's actual pretrained set. The original build spec listed
            # IRBBB/CRBBB but those don't exist in ecglib 1.0.1 — it ships RBBB
            # and LBBB instead (general right/left bundle branch block).
            pathologies = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC']

            here = os.path.dirname(os.path.abspath(__file__))
            default_dir = os.path.abspath(
                os.path.join(here, '..', '..', 'models_weights', 'ecg_finetuned'))
            finetuned_dir = os.environ.get('ECG_FINETUNED_DIR', default_dir)

            self._ecg_models = {}
            ft_loaded = 0
            for p in pathologies:
                try:
                    m = create_model(
                        model_name='densenet1d121',
                        pathology=p,
                        pretrained=True,
                    )
                    ft_path = os.path.join(finetuned_dir, f'{p}.pt')
                    if os.path.exists(ft_path):
                        ft_loaded += 1
                        # Snapshot pristine weights first: load_state_dict
                        # copies matching keys BEFORE raising on a key
                        # mismatch, so a bad file could otherwise leave the
                        # model partially overwritten.
                        pristine = {
                            k: v.detach().clone()
                            for k, v in m.state_dict().items()
                        }
                        try:
                            state = torch.load(ft_path, map_location='cpu')
                            if isinstance(state, dict) and 'state_dict' in state:
                                state = state['state_dict']
                            m.load_state_dict(state)
                            logger.info(
                                "ECG model %s: fine-tuned weights loaded from %s",
                                p, ft_path)
                            print(f"ECG {p}: fine-tuned weights loaded ({ft_path})")
                        except Exception as fe:
                            m.load_state_dict(pristine)
                            logger.warning(
                                "ECG model %s: failed to load fine-tuned weights "
                                "from %s (%s) — restored ecglib pretrained weights",
                                p, ft_path, fe)
                    m.eval()
                    m.to(self.get_device())
                    self._ecg_models[p] = m
                    logger.info("ECG model loaded: %s", p)
                except Exception as e:
                    logger.warning("Failed to load ECG model for %s: %s", p, e)
                    print(f"Warning: Failed to load ECG model for {p}: {e}")
            if ft_loaded == 0:
                logger.warning(
                    "ECG: no fine-tuned per-pathology checkpoints found in %s — "
                    "running STOCK ecglib weights. The headline macro-F1 0.727 "
                    "operating point depends on the fine-tuned checkpoints; see "
                    "Colab PFE/README.md.", finetuned_dir)
                print("WARNING: using STOCK ecglib ECG weights; fine-tuned checkpoints absent.")
            logger.info(
                "ECG models loaded: %d of %d (%d fine-tuned)",
                len(self._ecg_models), len(pathologies), ft_loaded)
        return self._ecg_models

    # ---- Echocardiography (EchoNet-Dynamic) ----------------------------

    def get_echo_models(self):
        """Return (seg_model, ef_model) for EchoNet-Dynamic.

        Source: Ouyang et al., Nature 2020 (github.com/echonet/dynamic).
            * seg  = DeepLabV3-ResNet50, 1 output channel (LV segmentation)
            * ef   = R(2+1)D-18 video model, 1 output (ejection-fraction regression)

        Weights are NOT bundled. Place the two pretrained checkpoints on disk and
        point to them via env vars, else they default to
        backend/models_weights/echonet/:
            ECHONET_SEG_WEIGHTS  (default: echonet_seg.pt)
            ECHONET_EF_WEIGHTS   (default: echonet_ef.pt)
        Raises a clear error if a checkpoint is missing.
        """
        if self._echo_seg is not None and self._echo_ef is not None:
            return self._echo_seg, self._echo_ef

        import os
        import torch
        import torch.nn as nn
        from torchvision.models.segmentation import deeplabv3_resnet50
        from torchvision.models.video import r2plus1d_18

        here = os.path.dirname(os.path.abspath(__file__))
        weights_dir = os.path.abspath(os.path.join(here, '..', '..', 'models_weights', 'echonet'))
        seg_path = os.environ.get('ECHONET_SEG_WEIGHTS', os.path.join(weights_dir, 'echonet_seg.pt'))
        ef_path = os.environ.get('ECHONET_EF_WEIGHTS', os.path.join(weights_dir, 'echonet_ef.pt'))
        for label, p in (('segmentation', seg_path), ('EF', ef_path)):
            if not os.path.exists(p):
                raise FileNotFoundError(
                    f'EchoNet {label} weights not found at: {p}\n'
                    f'Download the EchoNet-Dynamic checkpoints and place them there, '
                    f'or set the ECHONET_SEG_WEIGHTS / ECHONET_EF_WEIGHTS env vars.'
                )

        device = self.get_device()

        def _load_state(model, path):
            ckpt = torch.load(path, map_location=device)
            sd = ckpt.get('state_dict', ckpt) if isinstance(ckpt, dict) else ckpt
            sd = {k.replace('module.', '', 1): v for k, v in sd.items()}
            model.load_state_dict(sd)
            model.eval()
            model.to(device)
            return model

        print('Loading EchoNet-Dynamic models (segmentation + EF)...')
        logger.info('Loading EchoNet segmentation from %s', seg_path)
        seg = deeplabv3_resnet50(weights=None, weights_backbone=None, aux_loss=False)
        seg.classifier[-1] = nn.Conv2d(256, 1, kernel_size=1)
        self._echo_seg = _load_state(seg, seg_path)

        logger.info('Loading EchoNet EF model from %s', ef_path)
        ef = r2plus1d_18(weights=None)
        ef.fc = nn.Linear(ef.fc.in_features, 1)
        self._echo_ef = _load_state(ef, ef_path)

        logger.info('EchoNet models loaded on %s', device)
        return self._echo_seg, self._echo_ef

    # ---- EEG harmful-brain-activity classifier (BIOT, IIIC 6-class) ----

    def get_eeg_model(self):
        """Return the BIOT IIIC 6-class classifier (encoder + fine-tuned head).

        Source: BIOT — Biosignal Transformer (Yang et al., NeurIPS 2023,
            github.com/ycq091044/BIOT). The encoder is BIOT's *released* pretrained
            checkpoint (EEG-PREST-16-channels). The 6-class IIIC head is NOT released
            by BIOT — it is fine-tuned on the Kaggle HMS dataset via
            ``tools/train_eeg_head.py`` and saved to disk.

        Two on-disk checkpoints (mirrors the EchoNet weights pattern):
            BIOT_ENCODER_WEIGHTS  (default: models_weights/biot/EEG-PREST-16-channels.ckpt)
                the pretrained encoder — bundled in the repo.
            BIOT_IIIC_WEIGHTS     (default: models_weights/biot/biot_iiic.pt)
                the fine-tuned BIOTClassifier state_dict — NOT bundled.

        Raises a clear FileNotFoundError (pointing at the trainer) if the fine-tuned
        head is absent, so the EEG endpoint fails honestly rather than returning the
        predictions of a randomly-initialised head.
        """
        if self._eeg is not None:
            return self._eeg

        import os
        import torch
        from .biot import BIOTClassifier

        here = os.path.dirname(os.path.abspath(__file__))
        weights_dir = os.path.abspath(os.path.join(here, '..', '..', 'models_weights', 'biot'))
        encoder_path = os.environ.get(
            'BIOT_ENCODER_WEIGHTS', os.path.join(weights_dir, 'EEG-PREST-16-channels.ckpt'))
        iiic_path = os.environ.get(
            'BIOT_IIIC_WEIGHTS', os.path.join(weights_dir, 'biot_iiic.pt'))

        device = self.get_device()
        model = BIOTClassifier(n_classes=6, n_channels=16, n_fft=200, hop_length=100)

        # Pretrained encoder (bundled). Loaded into .biot exactly like BIOT's own
        # run_multiclass_supervised.py does.
        if not os.path.exists(encoder_path):
            raise FileNotFoundError(
                f'BIOT pretrained encoder not found at: {encoder_path}\n'
                f'It should ship in the repo; set BIOT_ENCODER_WEIGHTS to override.')
        logger.info('Loading BIOT encoder from %s', encoder_path)
        model.biot.load_state_dict(torch.load(encoder_path, map_location=device))

        # Fine-tuned IIIC head (NOT bundled).
        if not os.path.exists(iiic_path):
            raise FileNotFoundError(
                f'BIOT IIIC 6-class head not found at: {iiic_path}\n'
                f'BIOT does not release an IIIC classifier head, only the encoder. '
                f'Train one on the Kaggle HMS dataset:\n'
                f'    python tools/train_eeg_head.py --hms-dir <data> --out {iiic_path}\n'
                f'or point BIOT_IIIC_WEIGHTS at an existing fine-tuned checkpoint.')
        logger.info('Loading BIOT IIIC head from %s', iiic_path)
        state = torch.load(iiic_path, map_location=device)
        state = state.get('state_dict', state) if isinstance(state, dict) else state
        model.load_state_dict(state)

        model.eval()
        model.to(device)
        self._eeg = model
        logger.info('BIOT IIIC classifier loaded on %s', device)
        return self._eeg

    # ---- batch warm-up -------------------------------------------------

    def warmup(self):
        """Force-load every model up front (useful at server boot)."""
        logger.info("Warming up all models...")
        self.get_mri_segmentation_model()
        self.get_mri_classifier()
        self.get_ecg_models()
        logger.info("Warmup complete")
