import api from './api.js';

// Pull the server's suggested download name out of the Content-Disposition
// header (exposed cross-origin via CORS_EXPOSE_HEADERS on the backend).
function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback;
  const match = /filename\*?=(?:UTF-8'')?"?([^";\n]+)"?/i.exec(disposition);
  if (!match) return fallback;
  try {
    return decodeURIComponent(match[1].trim());
  } catch {
    return match[1].trim();
  }
}

// Trigger a client-side download from a blob + filename (the converter output
// is download-only; the technician re-uploads it on the normal modality page).
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const conversionService = {
  // POST /api/convert/<modality>/ as multipart. responseType 'blob' so the
  // standardized file streams straight back for download. On a converter error
  // the server returns a JSON envelope — axios still gives a Blob, which the
  // caller parses (see ConvertPage's error handling).
  async convert(modality, file, params = {}) {
    const form = new FormData();
    form.append('file', file);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && `${value}`.trim() !== '') {
        form.append(key, value);
      }
    });
    const resp = await api.post(`/convert/${modality}/`, form, {
      responseType: 'blob',
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const filename = filenameFromDisposition(
      resp.headers['content-disposition'], `${modality}_converted`,
    );
    return { blob: resp.data, filename };
  },

  // Smartwatch single-lead ECG PDF: the server returns JSON (screening + trace
  // preview + the CSV text embedded), not a file download — so the Convert page
  // can show a result inline and offer the CSV via a Download button.
  async convertEcgPdf(file) {
    const form = new FormData();
    form.append('file', file);
    const resp = await api.post('/convert/ecg/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return resp.data;
  },
};

export default conversionService;
