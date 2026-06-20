"""SHAP attribution (Captum GradientShap) for the EchoNet-Dynamic EF model.

Mirrors ``ecg_shap.py`` / ``shap_attr.py``: GradientShap is the fast, faithful,
gradient-based SHAP variant — appropriate for a deep net on our synchronous CPU
path (coalition methods like KernelSHAP are infeasible on a 3x32x112x112 video
clip in the request thread).

The EF model (R(2+1)D-18) is a SINGLE-output *regression* head (ejection fraction
%), so we attribute ``target=0`` (the one output) — not an argmax over classes.
The spatiotemporal attribution ``(1, 3, T, H, W)`` is reduced over the channel
axis to a ``(T, H, W)`` saliency volume normalised to [0, 1] ("which frames and
which regions of the 2D view drove the EF estimate"), and can be collapsed to a
per-frame importance vector.

HONESTY: this is signal/pixel-level saliency over a single 2D ultrasound plane —
which frames and image regions the model attended to — NOT regional wall-motion
analysis and NOT a clinical rationale.
"""
import numpy as np
import torch


def echo_gradient_shap(ef_model, clip_3thw, n_samples=8):
    """Compute a spatiotemporal SHAP saliency volume for the EF model via GradientShap.

    Must NOT be called under ``torch.no_grad()``: GradientShap needs an
    autograd-enabled context for the model forward (it backpropagates).

    THREAD-SAFETY: like ``swin_gradient_shap``/``ecg_gradient_shap``, this backprops
    on the shared EF model singleton (accumulating ``param.grad``). Safe today only
    because echo inference is synchronous and single-threaded — do not parallelize
    echo requests without revisiting this.

    Args:
        ef_model: the R(2+1)D-18 EchoNet EF regressor (single output).
        clip_3thw: (3, T, H, W) float array — the normalised clip the EF model sees
            during normal inference (same construction as ``_predict_ef``).
        n_samples: GradientShap samples (more = smoother, slower). Kept small by
            default — the video model is heavy on CPU.

    Returns:
        np.ndarray float32 (T, H, W) saliency volume, values in [0, 1].
    """
    from captum.attr import GradientShap
    device = next(ef_model.parameters()).device
    clip = np.asarray(clip_3thw, dtype=np.float32)
    x = torch.from_numpy(clip).float().unsqueeze(0).to(device)  # (1, 3, T, H, W)

    def forward(inp):
        out = ef_model(inp)
        if isinstance(out, tuple):
            out = out[0]
        if out.dim() == 1:
            out = out.unsqueeze(1)  # (N,) -> (N, 1) so target=0 indexes the EF output
        return out

    # Two-point baseline: all-zeros + the clip-mean constant; GradientShap
    # interpolates between them (mirrors the black + channel-mean MRI/ECG baseline).
    baselines = torch.cat(
        [torch.zeros_like(x), torch.full_like(x, float(x.mean().item()))], dim=0)
    attr = GradientShap(forward).attribute(
        x, baselines=baselines, target=0, n_samples=int(n_samples), stdevs=0.09)
    a = attr.detach()[0].abs().sum(dim=0)  # sum over channel axis -> (T, H, W)
    a = a - a.min()
    return (a / (a.max() + 1e-8)).cpu().numpy().astype(np.float32)


def frame_importance(attr_thw):
    """Reduce a (T, H, W) saliency volume to a per-frame importance vector.

    Σ|attribution| over (H, W) per frame, normalised so the most important frame =
    1.0 — answers "which frames (≈ systole/diastole phase) drove the EF estimate".

    Args:
        attr_thw: (T, H, W) array of (non-negative) attributions.

    Returns:
        np.ndarray float32 (T,) with values in [0, 1].
    """
    a = np.abs(np.asarray(attr_thw, dtype=np.float32))
    s = a.reshape(a.shape[0], -1).sum(axis=1)  # (T,)
    return (s / (s.max() + 1e-8)).astype(np.float32)
