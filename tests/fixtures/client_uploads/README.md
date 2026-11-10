# Client upload fixtures (multi-file battery)

Drop any retail CSV/XLSX here. The matrix test
`tests/test_client_upload_matrix.py` discovers every `*.csv` / `*.xlsx` in this
folder and runs upload → settings → profile → proposals → overview → grounded
assistant checks with `GEMINI_API_KEY` unset.

Egypt sample files are symlinked from `/home/youssef/code/test/` for local runs.
Add up to ~10 client files when ready; no code change required.
