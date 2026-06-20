"""Multimodal AI inference engine for MRI, ECG, Echo, and EEG analysis.

Exposes the top-level pipeline entry points, the model-loader singleton,
and a helper that wraps any pipeline call in a hard timeout.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from .ecg_pipeline import analyze_ecg, explain_ecg
from .echo_pipeline import analyze_echo, explain_echo
from .eeg_pipeline import analyze_eeg, explain_eeg
from .model_loader import ModelLoader
from .mri_pipeline import analyze_mri, explain_mri

__all__ = [
    'analyze_mri', 'explain_mri', 'analyze_ecg', 'explain_ecg',
    'analyze_echo', 'explain_echo', 'analyze_eeg', 'explain_eeg',
    'ModelLoader', 'run_inference_with_timeout',
]


def run_inference_with_timeout(func, file_path, timeout_seconds: int = 300) -> dict:
    """Run an inference pipeline with a hard timeout.

    The underlying inference work runs on a worker thread; if it doesn't finish
    in `timeout_seconds`, the caller gets a failure dict and the worker thread
    is abandoned (Python can't actually kill a running thread, so we just stop
    waiting and let the OS reclaim it when the process exits).

    Args:
        func: a callable like analyze_mri or analyze_ecg.
        file_path: argument forwarded to func.
        timeout_seconds: max wall-clock time before returning a TimeoutError dict.
    Returns:
        The result dict from func, OR a failure dict if it timed out.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, file_path)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeout:
            return {
                'status': 'failed',
                'error': f'Inference exceeded {timeout_seconds}s timeout',
                'error_type': 'TimeoutError',
            }
    finally:
        executor.shutdown(wait=False)
