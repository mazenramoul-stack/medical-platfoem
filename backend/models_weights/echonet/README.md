# EchoNet-Dynamic weights

Place the two pretrained checkpoints here so the Echo modality can load them:

- `echonet_seg.pt`  — DeepLabV3-ResNet50 LV segmentation
- `echonet_ef.pt`   — R(2+1)D-18 ejection-fraction regression

Source: https://github.com/echonet/dynamic (Ouyang et al., Nature 2020).
The repo's released checkpoints are commonly named like
`deeplabv3_resnet50_random.pt` and `r2plus1d_18_32_2_pretrained.pt` — rename them
to the two names above, **or** point at them with environment variables instead:

```
ECHONET_SEG_WEIGHTS=C:\path\to\deeplabv3_resnet50_random.pt
ECHONET_EF_WEIGHTS=C:\path\to\r2plus1d_18_32_2_pretrained.pt
```

The loader (`apps/inference/model_loader.py → get_echo_models`) checks the env
vars first, then falls back to this folder. It raises a clear error if a
checkpoint is missing.

Also required (one-time):  `pip install opencv-python-headless`  (video decoding).
