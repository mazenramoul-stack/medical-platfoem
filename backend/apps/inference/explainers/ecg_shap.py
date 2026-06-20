"""SHAP attribution (Captum GradientShap) for the 1-D DenseNet ECG classifiers.

Mirrors ``shap_attr.py`` (the Swin MRI explainer): GradientShap is the fast,
faithful, gradient-based SHAP variant — appropriate for a deep net on our
synchronous CPU path (a 12x5000 = 60,000-feature signal makes coalition methods
like KernelSHAP/LIME infeasible in the request thread).

Each ecglib pathology model is a single-output (sigmoid) binary classifier, so we
attribute ``target=0`` (the one logit). The signed pixel attributions are reduced
to a [12, 5000] saliency map (abs over the attribution), normalised to [0, 1],
and can be collapsed to a per-lead importance vector.
"""
import numpy as np
import torch


def ecg_gradient_shap(model, signal, n_samples=32):
    """Compute a SHAP saliency map for one ECG pathology model via GradientShap.

    Must NOT be called under ``torch.no_grad()``: GradientShap needs an
    autograd-enabled context for the model forward (it backpropagates).

    THREAD-SAFETY: like ``swin_gradcam``/``swin_gradient_shap``, this backprops on
    the shared model singleton (accumulating ``param.grad``). Safe today only
    because inference is synchronous and single-threaded — do not parallelize ECG
    requests without revisiting this.

    Args:
        model: an ecglib DenseNet-1D classifier (single sigmoid output).
        signal: (12, 5000) float array — the preprocessed 12-lead signal the model
            sees during normal inference.
        n_samples: GradientShap samples (more = smoother, slower).

    Returns:
        np.ndarray float32 [12, 5000] saliency map, values in [0, 1].
    """
    from captum.attr import GradientShap
    device = next(model.parameters()).device
    sig = np.asarray(signal, dtype=np.float32)
    x = torch.from_numpy(sig).float().unsqueeze(0).to(device)  # (1, 12, 5000)

    def forward(inp):
        out = model(inp)
        if isinstance(out, tuple):
            out = out[0]
        if out.dim() == 1:
            out = out.unsqueeze(1)  # (N,) -> (N, 1) so target=0 indexes the logit
        return out

    # Two-point baseline: all-zeros + the signal-mean constant; GradientShap
    # interpolates between them (mirrors the black + channel-mean MRI baseline).
    baselines = torch.cat(
        [torch.zeros_like(x), torch.full_like(x, float(x.mean().item()))], dim=0)
    attr = GradientShap(forward).attribute(
        x, baselines=baselines, target=0, n_samples=int(n_samples), stdevs=0.09)
    a = attr.detach()[0].abs()  # (12, 5000)
    a = a - a.min()
    return (a / (a.max() + 1e-8)).cpu().numpy().astype(np.float32)


def per_lead_importance(attr_map, lead_names):
    """Reduce a [12, 5000] saliency map to a per-lead importance dict.

    Σ|attribution| over time per lead, normalised so the most important lead = 1.0
    — answers "which of I…V6 drove the call".

    Args:
        attr_map: (12, T) array of (non-negative) attributions.
        lead_names: list of 12 lead labels in row order.

    Returns:
        dict {lead_name: importance in [0, 1]}.
    """
    a = np.abs(np.asarray(attr_map, dtype=np.float32))
    s = a.sum(axis=1)  # (12,)
    s = s / (s.max() + 1e-8)
    return {lead: float(v) for lead, v in zip(lead_names, s)}
