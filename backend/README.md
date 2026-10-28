# Backend source

The live Flask backend remains at the repository root (`app.py`,
`app_overrides.py`, `ml_pipeline.py`, `voice_server.py`, and
`voice_config.py`). This preserves the existing import paths and Vercel entry
point without changing application code.

This directory is reserved for a future package migration, which should be
performed together with explicit import and deployment updates.
