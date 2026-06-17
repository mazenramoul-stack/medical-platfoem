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
