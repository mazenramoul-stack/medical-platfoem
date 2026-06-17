"""Hook-based Grad-CAM for the HuggingFace Swin MRI classifier.

Swin's final LayerNorm emits a token sequence [B, L, C] (L = 7*7 for 224px input),
so a plain CNN Grad-CAM does not apply: we fold L back to a 7x7 grid, weight channels
by their mean gradient, ReLU, and normalise to [0,1]. The forward/backward run OUTSIDE
torch.no_grad() (the pipeline's classifier forward is under no_grad and cannot backprop).
"""
import numpy as np
import torch


def _resolve_target_layer(model):
    swin = getattr(model, "swin", model)
    layer = getattr(swin, "layernorm", None)
    if layer is None:
        raise RuntimeError("Grad-CAM: could not resolve Swin target layer (model.swin.layernorm)")
    return layer


def swin_gradcam(processor, model, pil_image, target_class=None):
    """Return (heatmap[h,w] float32 in [0,1], pred_idx, confidence, peak (nx,ny) in [0,1])."""
    device = next(model.parameters()).device
    inputs = processor(images=pil_image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    target_layer = _resolve_target_layer(model)

    store = {}
    h_fwd = target_layer.register_forward_hook(lambda m, i, o: store.__setitem__("act", o))
    h_bwd = target_layer.register_full_backward_hook(lambda m, gi, go: store.__setitem__("grad", go[0]))
    try:
        model.zero_grad(set_to_none=True)
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        idx = int(probs.argmax(dim=-1).item()) if target_class is None else int(target_class)
        conf = float(probs[0, idx].item())
        logits[0, idx].backward()
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
