# Agent notes

- Single Python/Streamlit app, not a package workspace. `app.py` is the UI entrypoint; market adapters, option analytics, volatility views and funding are root-level modules.
- Use the project Conda environment (`py4fi`). Run with `conda run -n py4fi python -m streamlit run app.py` (or `start_dashboard.bat`).
- Full test suite: `conda run -n py4fi python -m unittest discover -s tests -v`. Focused: `... -p "test_analytics.py" -v`.
- Runtime dependencies are in `requirements.txt`; no lint, typecheck or build command is configured.
- `app.py` loads `.env` from the repo root. Keep credentials in ignored `.env`/Streamlit secrets; `.env.example` documents names. Never add secrets to fixtures or research artifacts.
- Tests use synthetic fixtures and mocked API responses. Live Alpaca checks need credentials and feed entitlements; BYMA is public. See `GUIDE.md`.
- `research/` holds dated data-source checks and snapshots; `reports/` holds one-off analysis outputs. The GGAL forecasting model lives in a separate repo (`options-valuation-model`).
