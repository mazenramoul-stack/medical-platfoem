"""Hook-based Grad-CAM for the HuggingFace Swin MRI classifier.

Swin's final LayerNorm emits a token sequence [B, L, C] (L = 7*7 for 224px input),
so a plain CNN Grad-CAM does not apply: we fold L back to a 7x7 grid, weight channels
by their mean gradient, ReLU, and normalise to [0,1]. The forward/backward run OUTSIDE
torch.no_grad() (the pipeline's classifier forward is under no_grad and cannot backprop).
"""
import numpy as np
import torch


def _resolve_target_layer(model):
    swin = getattr(model, "swin", None)
    if swin is None:
        raise RuntimeError(
            "Grad-CAM: model has no .swin attribute — expected a HuggingFace "
            "SwinForImageClassification wrapper")
    layer = getattr(swin, "layernorm", None)
    if layer is None:
        raise RuntimeError("Grad-CAM: model.swin has no .layernorm attribute")
    return layer


def swin_gradcam(processor, model, pil_image, target_class=None):
    """Compute Grad-CAM on the Swin classifier's final LayerNorm.

    Not thread-safe: calls ``model.zero_grad()`` on the shared model singleton,
    so callers must not issue concurrent Grad-CAM requests (the platform's
    inference is synchronous, so this holds today).

    Args:
        processor: HuggingFace AutoImageProcessor for the Swin model.
        model: HuggingFace SwinForImageClassification (eval mode is fine).
        pil_image: PIL Image; the processor handles resizing/normalisation.
        target_class: Class index to backpropagate; if None, the predicted
            class (argmax of softmax) is used.

    Returns:
        Tuple ``(cam, pred_idx, confidence, peak)``:
            cam: np.ndarray float32 [side, side], values in [0, 1].
            pred_idx: predicted (or requested) class index.
            confidence: softmax probability of pred_idx.
            peak: (nx, ny) normalised peak coordinates, each in [0, 1].

    Raises:
        RuntimeError: if the target layer can't be resolved, no gradient is
            captured, or the token grid is not square.
    """
    device = next(model.parameters()).device
    inputs = processor(images=pil_image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    target_layer = _resolve_target_layer(model)

    store = {}

    def _save_act(_m, _i, output):
        store["act"] = output

    def _save_grad(_m, _gi, grad_output):
        store["grad"] = grad_output[0]

    h_fwd = target_layer.register_forward_hook(_save_act)
    h_bwd = target_layer.register_full_backward_hook(_save_grad)
    try:
        model.zero_grad(set_to_none=True)
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        idx = int(probs.argmax(dim=-1).item()) if target_class is None else int(target_class)
        conf = float(probs[0, idx].item())
        logits[0, idx].backward()
        if store.get("act") is None or store.get("grad") is None:
            raise RuntimeError(
                "Grad-CAM: hooks captured no activation/gradient — ensure the model "
                "is not running under torch.no_grad().")
        act = store["act"].detach()[0]    # (L, C)
        grad = store["grad"].detach()[0]  # (L, C)
    finally:
        h_fwd.remove()
        h_bwd.remove()

    L, _ = act.shape
    side = int(round(L ** 0.5))
    if side * side != L:
        raise RuntimeError(f"Grad-CAM: token length {L} is not a square grid")
    weights = grad.mean(dim=0)                       # (C,)
    cam = torch.relu((act * weights).sum(dim=-1)).reshape(side, side)
    cam = cam - cam.min()
    cam = (cam / (cam.max() + 1e-8)).cpu().numpy().astype(np.float32)
    py, px = np.unravel_index(int(cam.argmax()), cam.shape)
    peak = ((px + 0.5) / side, (py + 0.5) / side)    # normalized (nx, ny)
    return cam, idx, conf, peak
