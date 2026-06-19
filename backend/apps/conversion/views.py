"""Technician-only data-conversion endpoint (mounted at /api/convert/).

    POST /api/convert/<modality>/   multipart {file, ...modality params}
        -> 200 with the standardized file as an attachment download, OR
        -> 4xx/422 with a {status, error, error_type} envelope on bad input.

The output is download-only: it does NOT create an analysis record. The
technician re-uploads the standardized file through the normal modality pages.
"""

import logging
import os
import tempfile

from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .converters import CONVERTERS, ConversionError
from .permissions import IsTechnician

logger = logging.getLogger(__name__)

# Sane upload cap. Echo cines are the largest standard clinic file, so this
# matches the echo upload limit (500 MB).
MAX_CONVERT_UPLOAD_BYTES = 500 * 1024 * 1024


class ConvertView(APIView):
    """Dispatch a raw clinic file to the per-modality converter."""

    permission_classes = [IsTechnician]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, modality):
        modality = (modality or '').lower()
        convert = CONVERTERS.get(modality)
        if convert is None:  # defense in depth — the URL already restricts these
            return self._fail('Unknown modality: %s.' % modality, 'UnknownModality',
                              status.HTTP_404_NOT_FOUND)

        uploaded = request.FILES.get('file')
        if uploaded is None:
            return self._fail('file is required.', 'MissingFile',
                              status.HTTP_400_BAD_REQUEST)
        if uploaded.size > MAX_CONVERT_UPLOAD_BYTES:
            return self._fail(
                f'File too large ({uploaded.size} bytes). '
                f'Max: {MAX_CONVERT_UPLOAD_BYTES} bytes.',
                'FileTooLarge', status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        # Modality params (e.g. MRI slice_index) arrive as multipart form fields.
        params = {k: v for k, v in request.data.items() if k != 'file'}

        # Everything happens inside one temp dir; converters write the output
        # alongside the input, and the whole dir is removed on context exit so
        # no stray files are left behind.
        with tempfile.TemporaryDirectory(prefix='convert_') as workdir:
            in_name = os.path.basename(uploaded.name or 'upload') or 'upload'
            in_path = os.path.join(workdir, in_name)
            with open(in_path, 'wb') as fh:
                for chunk in uploaded.chunks():
                    fh.write(chunk)

            try:
                out_path, meta = convert(in_path, **params)
            except ConversionError as e:
                logger.info('convert %s rejected input: %s', modality, e)
                return self._fail(str(e), getattr(e, 'error_type', 'ConversionError'),
                                  status.HTTP_422_UNPROCESSABLE_ENTITY)
            except Exception as e:  # never 500 on bad input — mirror Contract 2
                logger.exception('convert %s crashed', modality)
                return self._fail(str(e) or 'Conversion failed.',
                                  type(e).__name__, status.HTTP_422_UNPROCESSABLE_ENTITY)

            with open(out_path, 'rb') as fh:
                payload = fh.read()

        content_type = meta.get('content_type', 'application/octet-stream')
        download_name = meta.get('filename') or os.path.basename(out_path)
        resp = HttpResponse(payload, content_type=content_type)
        resp['Content-Disposition'] = f'attachment; filename="{download_name}"'
        # Let the browser (cross-origin: Vercel -> HF Space) read the filename.
        resp['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return resp

    @staticmethod
    def _fail(error, error_type, http_status):
        return Response(
            {'status': 'failed', 'error': error, 'error_type': error_type},
            status=http_status,
        )
