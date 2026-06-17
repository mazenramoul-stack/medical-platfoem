import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from django.test import SimpleTestCase
from apps.inference.model_loader import ModelLoader
from apps.inference.explainers.gradcam import swin_gradcam

BACKEND_DIR = Path(__file__).resolve().parent.parent
MRI_WEIGHTS = BACKEND_DIR / "models_weights" / "vit_brain_tumor" / "model.safetensors"


@unittest.skipUnless(MRI_WEIGHTS.exists(), f"Missing MRI classifier weights at {MRI_WEIGHTS}")
class GradCamTest(SimpleTestCase):
    def test_gradcam_shape_and_range(self):
        processor, model = ModelLoader().get_mri_classifier()
        img = Image.fromarray((np.random.rand(224, 224, 3) * 255).astype("uint8"))
        cam, idx, conf, peak = swin_gradcam(processor, model, img)
        self.assertEqual(cam.ndim, 2)
        self.assertGreaterEqual(cam.min(), 0.0)
        self.assertLessEqual(cam.max(), 1.0 + 1e-6)
        self.assertIn(idx, range(model.config.num_labels))
        self.assertTrue(0.0 <= peak[0] <= 1.0 and 0.0 <= peak[1] <= 1.0)
