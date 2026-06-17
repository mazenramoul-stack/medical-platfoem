import numpy as np
from django.test import SimpleTestCase
from apps.inference.explainers.base import attribution_agreement, resize_to

class AgreementTest(SimpleTestCase):
    def test_identical_maps_agree(self):
        a = np.random.rand(7, 7).astype("float32")
        out = attribution_agreement(a, a.copy())
        self.assertAlmostEqual(out["spearman"], 1.0, places=5)
        self.assertAlmostEqual(out["topk_iou"], 1.0, places=5)

    def test_resize_changes_shape_only(self):
        a = np.random.rand(7, 7).astype("float32")
        b = resize_to(a, (224, 224))
        self.assertEqual(b.shape, (224, 224))

    def test_peak_xy_locates_max(self):
        from apps.inference.explainers.base import heatmap_peak_xy
        cam = np.zeros((10, 10), dtype="float32"); cam[8, 2] = 1.0  # row 8, col 2
        nx, ny = heatmap_peak_xy(cam)
        self.assertAlmostEqual(nx, (2 + 0.5) / 10, places=6)   # x from column
        self.assertAlmostEqual(ny, (8 + 0.5) / 10, places=6)   # y from row

    def test_agreement_constant_maps_nan_guard(self):
        a = np.ones((7, 7), dtype="float32"); b = np.ones((7, 7), dtype="float32")
        out = attribution_agreement(a, b)
        self.assertEqual(out["spearman"], 0.0)   # NaN correlation -> 0.0

    def test_resize_preserves_range(self):
        a = np.random.rand(7, 7).astype("float32")
        b = resize_to(a, (32, 32))
        self.assertGreaterEqual(b.min(), 0.0)
        self.assertLessEqual(b.max(), 1.0)

    def test_overlay_returns_figure(self):
        from matplotlib.figure import Figure
        from apps.inference.explainers.base import gradcam_overlay_figure
        img = (np.random.rand(20, 20, 3) * 255).astype("uint8")
        cam = np.random.rand(7, 7).astype("float32")
        fig = gradcam_overlay_figure(img, cam)
        self.assertIsInstance(fig, Figure)
        import matplotlib.pyplot as plt; plt.close(fig)
