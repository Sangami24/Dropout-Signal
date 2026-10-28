# Project structure

```text
Dropout Signal/
├── app.py, app_overrides.py, ml_pipeline.py, voice_server.py, voice_config.py
│   └── Active Flask backend (kept at root to avoid code changes)
├── static/                 Active Flask static assets
├── datasets/               Active CSV datasets and catalog
├── docs/
│   ├── guides/             Startup and operational guidance
│   └── assets/             Architecture diagrams
├── notebooks/              Databricks notebooks
├── scripts/
│   ├── data/               Dataset retrieval helpers
│   ├── operations/         Tunnel and Twilio helpers
│   └── tools/              Supporting utilities
├── tests/
│   ├── integration/        Browser and end-to-end checks
│   └── manual/             Manual smoke-test helpers
├── artifacts/              Verification output and logs
├── archive/                Historical maintenance and FloraMind files
├── backend/                Reserved backend-package boundary
└── frontend/               Reserved standalone-frontend boundary
```

The active application files are intentionally not moved into `backend/` or
`frontend/`: doing so would require changing imports, static paths, and the
Vercel entry point. This reorganization preserves source contents exactly.
