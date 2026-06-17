"""Shared explainer helpers: heatmap resize, overlay figure, peak, agreement metrics."""
import numpy as np


def resize_to(arr, shape):
    """Bilinearly resize a 2D map to ``shape`` (H, W) without extra deps (via PIL).

    Args:
        arr: 2D array, values roughly in [0, 1].
        shape: target (height, width).

    Returns:
        np.ndarray float32 of the requested shape, values in [0, 1].
    """
    from PIL import Image
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype("uint8"))
    im = im.resize((shape[1], shape[0]), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0


def heatmap_peak_xy(cam):
    """Argmax of a 2D heatmap as normalized (nx, ny) in [0, 1] (x=col, y=row)."""
    h, w = cam.shape
    py, px = np.unravel_index(int(np.asarray(cam).argmax()), cam.shape)
    return ((px + 0.5) / w, (py + 0.5) / h)


def attribution_agreement(a, b, topk_frac=0.1):
    """Agreement between two heatmaps: Spearman rank-corr + top-k IoU.

    ``b`` is resized to ``a``'s shape first. Returns a dict
    ``{"spearman": float, "topk_iou": float}``; NaN correlation maps to 0.0.
    """
    from scipy.stats import spearmanr
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if b.shape != a.shape:
        b = resize_to(b, a.shape)
    af, bf = a.ravel(), b.ravel()
    rho = spearmanr(af, bf).correlation
    k = max(1, int(len(af) * topk_frac))
    ta, tb = set(np.argsort(af)[-k:]), set(np.argsort(bf)[-k:])
    iou = len(ta & tb) / len(ta | tb)
    return {"spearman": float(0.0 if rho != rho else rho), "topk_iou": float(iou)}


def gradcam_overlay_figure(image_rgb, cam):
    """Build a matplotlib Figure: ``image_rgb`` with a jet heatmap (``cam``) overlaid.

    Mirrors the red-overlay pattern in mri_pipeline.py. The caller saves the returned
    figure via utils.save_visualization and closes it.

    Args:
        image_rgb: (H, W, 3) uint8/float image.
        cam: 2D heatmap in [0, 1] (any size; resized to the image).

    Returns:
        matplotlib.figure.Figure (Agg backend; not yet saved/closed).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h, w = image_rgb.shape[:2]
    cam_up = resize_to(cam, (h, w))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.imshow(image_rgb)
    ax.imshow(cam_up, cmap="jet", alpha=0.40)
    ax.axis("off")
    return fig
