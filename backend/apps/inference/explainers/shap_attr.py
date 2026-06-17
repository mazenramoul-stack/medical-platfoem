"""SHAP attribution (Captum GradientShap) for the Swin MRI classifier.

GradientShap is the fast, faithful, gradient-based SHAP variant — appropriate for a deep
net and our synchronous CPU path (unlike KernelSHAP/LIME). Pixel attributions are reduced
to a [H, W] saliency map (abs sum over channels), normalised to [0, 1].
"""
import numpy as np
import torch


def swin_gradient_shap(processor, model, pil_image, target_class, n_samples=32):
    """Compute a SHAP saliency map for the Swin classifier via Captum GradientShap.

    Args:
        processor: HuggingFace AutoImageProcessor for the Swin model.
        model: HuggingFace SwinForImageClassification.
        pil_image: PIL Image; the processor handles resizing/normalisation.
        target_class: Class index to attribute.
        n_samples: GradientShap samples (more = smoother, slower).

    Returns:
        np.ndarray float32 [H, W] saliency map, values in [0, 1].
    """
    from captum.attr import GradientShap
    device = next(model.parameters()).device
    px = processor(images=pil_image, return_tensors="pt")["pixel_values"].to(device)

    def forward(pixel_values):
        return model(pixel_values=pixel_values).logits

    baselines = torch.cat([torch.zeros_like(px), torch.full_like(px, float(px.mean()))], dim=0)
    attr = GradientShap(forward).attribute(
        px, baselines=baselines, target=int(target_class), n_samples=int(n_samples), stdevs=0.09)
    a = attr.detach()[0].abs().sum(dim=0)            # (H, W)
    a = a - a.min()
    return (a / (a.max() + 1e-8)).cpu().numpy().astype(np.float32)
