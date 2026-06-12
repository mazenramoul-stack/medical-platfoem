"""Vendored subset of the BIOT model (Yang et al., NeurIPS 2023).

Only the BIOT model classes are vendored here — the upstream ``model/__init__.py``
also pulls in SPaRCNet/ContraWR/CNNTransformer/FFCL/STTransformer, none of which we
use. Keeping this slim avoids dragging in their dependencies.

Upstream: https://github.com/ycq091044/BIOT  (MIT License, (c) 2023 Chaoqi Yang)
See LICENSE in this directory for the full upstream license text.
"""

from .biot import BIOTClassifier, BIOTEncoder, UnsupervisedPretrain, SupervisedPretrain

__all__ = ["BIOTClassifier", "BIOTEncoder", "UnsupervisedPretrain", "SupervisedPretrain"]
