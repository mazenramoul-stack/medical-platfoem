"""Modality converters: standard clinic file -> exact format each model needs.

Each module exposes ``convert(input_path, **params) -> (output_path, meta)``.
``CONVERTERS`` maps the URL modality token to the callable; the view dispatches
through it.
"""

from .base import ConversionError
from .ecg import convert as convert_ecg
from .echo import convert as convert_echo
from .eeg import convert as convert_eeg
from .mri import convert as convert_mri

CONVERTERS = {
    'mri': convert_mri,
    'ecg': convert_ecg,
    'echo': convert_echo,
    'eeg': convert_eeg,
}

__all__ = ['CONVERTERS', 'ConversionError']
