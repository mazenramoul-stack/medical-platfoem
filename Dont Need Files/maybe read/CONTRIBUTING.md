# Contributing

This is an academic Master's project. External contributions are not actively
solicited, but if you're forking it for your own thesis or want to extend it,
here's the lay of the land.

## Code style

- **Python**: PEP 8, four-space indentation. Google-style docstrings on public
  functions in `apps/inference/`. Keep view methods short — push logic into
  serializers or pipelines.
- **JavaScript**: 2-space indentation, no semicolons-omitted style — Prettier
  defaults. Functional components only; no class components except `ErrorBoundary`.
- **CSS**: Tailwind utility classes inline. Custom CSS only when Tailwind can't
  express it.

## Branch hygiene

- `main` is the deployable branch.
- Feature work in `feature/<short-name>` branches.
- Avoid committing generated files: model weights (`backend/models_weights/`),
  uploaded media (`backend/media/{mri,ecg,echo,eeg}/`), downloaded datasets
  (`data/hms/`), test samples (`samples/`), or
  build artifacts (`frontend/dist/`, `node_modules/`).

## Adding a new modality

The platform was designed so a new modality (CT, genomics…) plugs in
without touching existing apps. Roughly:

1. **Pipeline** — create `apps/inference/<modality>_pipeline.py` exposing an
   `analyze_<modality>(file_path) -> dict` function with the standard
   `{status, ...result_fields, error?, error_type?}` contract.
2. **Model loader** — extend `ModelLoader` with a `get_<modality>_model()` lazy
   accessor.
3. **Django app** — `python manage.py startapp <modality> apps/<modality>`,
   register in `INSTALLED_APPS` as `apps.<modality>` (see existing apps' `apps.py`).
4. **Model + migration** — define a `<Modality>Analysis` model with
   `patient` FK, `file` FileField, status enum, `model_used`, `result_*` fields,
   `created_at`. Run `makemigrations` + `migrate`.
5. **Serializer + views** — copy `apps/mri/serializers.py` and `apps/mri/views.py`,
   adapt the file-validation tuple, allowed-extensions set, max size, and the
   field-mapping after inference.
6. **URL** — `path('api/<modality>/', include('apps.<modality>.urls'))` in
   `core/urls.py`.
7. **Frontend** — create `frontend/src/modules/<Modality>/` mirroring the
   MRI module (`<Modality>Upload.jsx`, `<Modality>Result.jsx`, `<Modality>History.jsx`).
   Add to `App.jsx` routes and `Sidebar.jsx` link list.
8. **Reports** — extend `apps/reports/pdf_generator.py` with a new section
   builder (`_<modality>_section()`) and call it from `build()`.

## Running tests

```bash
# Backend
cd backend
python manage.py test tests.test_pipelines --verbosity 2

# Frontend (build-time only — no Jest yet)
cd frontend
npm run build
```

The Django test suite uses `SimpleTestCase` for inference (no DB) and
`APITestCase` for HTTP endpoints (test DB auto-created). First run downloads
~600 MB of model weights; subsequent runs hit the local cache.

## Reporting issues

For PFE-internal issues, contact:
- Mazen Ramoul — `mazen.ramoul@univ-constantine2.dz`

For supervisor consultation:
- Prof. DERDOUR Makhlouf
- Prof. TALBI Hichem
