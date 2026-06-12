# BIOT / IIIC EEG weights

The EEG modality uses two checkpoints:

- `EEG-PREST-16-channels.ckpt` — **bundled.** BIOT's released pretrained *encoder*
  (16-channel, pretrained on 5M MGH resting-EEG samples). Source:
  https://github.com/ycq091044/BIOT (MIT). This is the genuinely-pretrained backbone.
- `biot_iiic.pt` — **NOT bundled.** The fine-tuned `BIOTClassifier` (encoder + the
  6-class IIIC head). BIOT does **not** release an IIIC classification head — only
  the encoder above — so this must be produced by fine-tuning the head on the public
  Kaggle "HMS — Harmful Brain Activity Classification" dataset (encoder frozen):

  ```
  # needs ~/.kaggle/kaggle.json and acceptance of the HMS competition rules
  python tools/train_eeg_head.py --download 600 --hms-dir data/hms \
      --out backend/models_weights/biot/biot_iiic.pt
  ```

  Or point at an existing fine-tuned checkpoint with environment variables:

  ```
  BIOT_ENCODER_WEIGHTS=C:\path\to\EEG-PREST-16-channels.ckpt
  BIOT_IIIC_WEIGHTS=C:\path\to\biot_iiic.pt
  ```

The loader (`apps/inference/model_loader.py → get_eeg_model`) checks the env vars
first, then falls back to this folder. It raises a clear `FileNotFoundError` if the
fine-tuned head (`biot_iiic.pt`) is missing — by design, so the endpoint fails
honestly rather than serving the output of an untrained (random) head.

Also required (one-time):  `pip install mne edfio linear-attention-transformer`.

Validate with:  `python tools/eval_eeg.py --hms-dir data/hms`  (balanced accuracy,
Cohen's κ, macro/weighted F1, per-class P/R/F1, 6×6 confusion, KL divergence).
