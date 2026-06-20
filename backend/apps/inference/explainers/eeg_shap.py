"""SHAP attribution (Captum GradientShap) for the BIOT IIIC EEG classifier.

Mirrors ``ecg_shap.py`` (the 1-D ECG explainer) and ``shap_attr.py`` (the Swin
MRI explainer): GradientShap is the fast, faithful, gradient-based SHAP variant —
appropriate for a deep net on our synchronous CPU path (a 16-channel x 2000-sample
EEG segment makes coalition methods like KernelSHAP/LIME infeasible in the request
thread).

BIOT is **multi-class** (6 IIIC softmax classes), so — like the Swin classifier and
unlike the single-sigmoid ECG models — we attribute a chosen ``target_class`` index.
GradientShap backprops through BIOT's STFT-based patch embedding (``torch.stft`` is
differentiable; verified on the real model). The signed sample attributions are
reduced to a [16, 2000] saliency map (abs over the attribution), normalised to
[0, 1], and can be collapsed to a per-channel importance vector.
"""
import numpy as np
import torch


def eeg_gradient_shap(model, signal, target_class=0, n_samples=32):
    """Compute a SHAP saliency map for one IIIC class via Captum GradientShap.

    Must NOT be called under ``torch.no_grad()``: GradientShap needs an
    autograd-enabled context for the model forward (it backpropagates).

    THREAD-SAFETY: like ``swin_gradcam``/``ecg_gradient_shap``, this backprops on
    the shared BIOT model singleton (accumulating ``param.grad``). Safe today only
    because inference is synchronous and single-threaded — do not parallelize EEG
    requests without revisiting this.

    Args:
        model: a BIOTClassifier (forward takes (N, 16, 2000) -> (N, 6) logits).
        signal: (16, 2000) float array — one preprocessed, normalised EEG segment
            in the exact shape BIOT sees during normal inference.
        target_class: IIIC class index in [0, 5] to attribute (argmax/predicted by
            the caller).
        n_samples: GradientShap samples (more = smoother, slower).

    Returns:
        np.ndarray float32 [16, 2000] saliency map, values in [0, 1].
    """
    from captum.attr import GradientShap
    device = next(model.parameters()).device
    sig = np.asarray(signal, dtype=np.float32)
    x = torch.from_numpy(sig).float().unsqueeze(0).to(device)  # (1, 16, 2000)

    def forward(inp):
        out = model(inp)
        if isinstance(out, tuple):
            out = out[0]
        if out.dim() == 1:
            out = out.unsqueeze(0)  # (6,) -> (1, 6) so target indexes a class
        return out

    # Two-point baseline: all-zeros + the signal-mean constant; GradientShap
    # interpolates between them (mirrors the black + channel-mean MRI/ECG baseline).
    baselines = torch.cat(
        [torch.zeros_like(x), torch.full_like(x, float(x.mean().item()))], dim=0)
    attr = GradientShap(forward).attribute(
        x, baselines=baselines, target=int(target_class),
        n_samples=int(n_samples), stdevs=0.09)
    a = attr.detach()[0].abs()  # (16, 2000)
    a = a - a.min()
    return (a / (a.max() + 1e-8)).cpu().numpy().astype(np.float32)


def per_channel_importance(attr_map, channel_names):
    """Reduce a [16, 2000] saliency map to a per-channel importance dict.

    Σ|attribution| over time per channel, normalised so the most important channel
    = 1.0 — answers "which electrodes drove the call".

    Args:
        attr_map: (16, T) array of (non-negative) attributions.
        channel_names: list of 16 bipolar channel labels in row order.

    Returns:
        dict {channel_name: importance in [0, 1]}.
    """
    a = np.abs(np.asarray(attr_map, dtype=np.float32))
    s = a.sum(axis=1)  # (16,)
    s = s / (s.max() + 1e-8)
    return {ch: float(v) for ch, v in zip(channel_names, s)}
