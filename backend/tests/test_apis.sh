#!/usr/bin/env bash
# End-to-end smoke test for the Multimodal Medical AI Platform API.
#
# Usage:
#   chmod +x backend/tests/test_apis.sh
#   ./backend/tests/test_apis.sh
#
# Prereqs:
#   - Django dev server running on http://localhost:8000 (or set $BASE_URL)
#   - User registered with EMAIL/PASSWORD (defaults below)
#   - jq installed (used for parsing JSON)
#   - Sample files present in backend/media/:
#       - mri/test_sample.png
#       - ecg/test_sample.csv
#
# Windows: run from Git Bash, WSL, or Cygwin. PowerShell users should use
# the Python equivalent script instead.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-doctor@test.local}"
PASSWORD="${PASSWORD:-SecurePass123!}"
MRI_FILE="${MRI_FILE:-backend/media/mri/test_sample.png}"
ECG_FILE="${ECG_FILE:-backend/media/ecg/test_sample.csv}"

say() { printf '\n=== %s ===\n' "$*"; }

# 1. Login
say "1. Login as $EMAIL"
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login/" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access)
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "Login failed."
    exit 1
fi
echo "access token length: ${#TOKEN}"

# 2. Create a patient
say "2. Create a patient"
PATIENT_ID=$(curl -s -X POST "$BASE_URL/api/patients/" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"full_name":"API Test Patient","age":45,"gender":"M","medical_history":"None"}' \
    | jq -r .id)
echo "patient_id=$PATIENT_ID"

# 3. Upload MRI
say "3. Upload MRI ($MRI_FILE)"
curl -s -X POST "$BASE_URL/api/mri/upload/" \
    -H "Authorization: Bearer $TOKEN" \
    -F "patient_id=$PATIENT_ID" \
    -F "file=@$MRI_FILE" \
    | jq '{id, status, tumor: .result_tumor_type, conf: .result_confidence, mask_url, overlay_url}'

# 4. List MRI for this patient
say "4. List MRI analyses for patient_id=$PATIENT_ID"
curl -s "$BASE_URL/api/mri/?patient_id=$PATIENT_ID" \
    -H "Authorization: Bearer $TOKEN" \
    | jq 'length as $n | "found \($n) MRI(s)"'

# 5. Upload ECG
say "5. Upload ECG ($ECG_FILE)"
curl -s -X POST "$BASE_URL/api/ecg/upload/" \
    -H "Authorization: Bearer $TOKEN" \
    -F "patient_id=$PATIENT_ID" \
    -F "file=@$ECG_FILE" \
    | jq '{id, status, diagnosis: .result_arrhythmia_type, conf: .result_confidence, plot_url}'

# 6. List ECG for this patient
say "6. List ECG analyses for patient_id=$PATIENT_ID"
curl -s "$BASE_URL/api/ecg/?patient_id=$PATIENT_ID" \
    -H "Authorization: Bearer $TOKEN" \
    | jq 'length as $n | "found \($n) ECG(s)"'

# 7. Patient history (joins MRI + ECG)
say "7. Patient history"
curl -s "$BASE_URL/api/patients/$PATIENT_ID/history/" \
    -H "Authorization: Bearer $TOKEN" \
    | jq '{patient_name, mri_count: (.mri_analyses | length), ecg_count: (.ecg_analyses | length)}'

say "Done."
