"""Regression: a reduced-lead ECG must be REJECTED, not faked into a diagnosis.

A <12-lead upload used to be padded (lead I broadcast across all 12 channels) and
fed to the 12-lead pathology models, producing a confident but meaningless result.
analyze_ecg now refuses it. This test is weight-free and CI-safe: the rejection
happens before any model is loaded, so no ~700 MB download is triggered.
"""

import os
import tempfile

import numpy as np
import pandas as pd
from django.test import SimpleTestCase


class ECGReducedLeadRejectTest(SimpleTestCase):
    def test_three_lead_csv_is_rejected_not_diagnosed(self):
        from apps.inference import analyze_ecg

        df = pd.DataFrame({"I": np.zeros(5000), "II": np.zeros(5000), "III": np.zeros(5000)})
        tmp = os.path.join(tempfile.gettempdir(), "ecg_reduced_lead_reject.csv")
        df.to_csv(tmp, index=False)
        try:
            result = analyze_ecg(tmp)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

        self.assertEqual(result.get("status"), "failed",
                         msg=f"reduced lead set should fail, got: {result}")
        self.assertEqual(result.get("error_type"), "InsufficientLeads")
        # Must NOT present a confident pathology diagnosis on broadcast data.
        self.assertIsNone(result.get("diagnosis"))
