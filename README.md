[README.md](https://github.com/user-attachments/files/30035424/README.md)
# MLOps Task 0 — Batch Signal Job

A minimal, reproducible batch job that reads OHLCV data, computes a rolling
mean on `close`, derives a binary trading signal, and writes structured
metrics + logs. Built for the Primetrade.ai / MetaStackerBandit technical
assessment.

## What it does

1. Loads and validates `config.yaml` (`seed`, `window`, `version`)
2. Loads and validates `data.csv` (must contain a `close` column)
3. Computes a rolling mean on `close` over `window` rows
4. Generates a binary signal: `1` if `close > rolling_mean`, else `0`
5. Writes `metrics.json` (success or error schema) and `run.log`

## Requirements

- Python 3.9+
- See `requirements.txt` (numpy, pandas, PyYAML)

## Local run

```bash
pip install -r requirements.txt
python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log
```

All paths are passed as CLI arguments — nothing is hard-coded, so any
input/config/output filenames or locations work.

### Handled error cases

The job validates inputs and writes an error-schema `metrics.json` (with
non-zero exit code) for:

- Missing input file
- Empty input file
- Invalid/malformed CSV
- Missing `close` column
- Missing config file
- Missing required config field(s) (`seed`, `window`, `version`)
- Invalid config structure (not a valid YAML mapping)

## Docker

Build:

```bash
docker build -t mlops-task .
```

Run:

```bash
docker run --rm mlops-task
```

The image bundles `data.csv` and `config.yaml`, runs the same CLI command
internally, prints the final metrics JSON to stdout, and exits `0` on
success or non-zero on failure.

## Rolling mean / NaN handling

The first `window - 1` rows do not have enough history for a full rolling
window. Their `rolling_mean` is `NaN` (standard pandas behavior with
`min_periods=window`), and they are **excluded** from the `signal_rate`
calculation in metrics, though they remain in the output row count
(`rows_processed` reflects total rows loaded, not just rows with a valid
signal). This keeps `signal_rate` an accurate average over rows that
actually had a defined signal.

## Determinism

`numpy.random.seed(seed)` is set from config immediately after config
validation. Given the same `data.csv` and `config.yaml`, `rows_processed`,
`signal_rate`, `seed`, and `version` are identical across runs. Only
`latency_ms` varies run-to-run, since it measures wall-clock execution time.

## Example `metrics.json` (success)

```json
{
  "version": "v1",
  "rows_processed": 10000,
  "metric": "signal_rate",
  "value": 0.4991,
  "latency_ms": 40,
  "seed": 42,
  "status": "success"
}
```

## Example `metrics.json` (error)

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found in input data"
}
```

## Files

| File | Purpose |
|---|---|
| `run.py` | Main batch job |
| `config.yaml` | Config (seed, window, version) |
| `data.csv` | Sample OHLCV input (10,000 rows) |
| `requirements.txt` | Pinned Python dependencies |
| `Dockerfile` | Container build definition |
| `README.md` | This file |
| `metrics.json` | Sample output from a successful run |
| `run.log` | Sample log from a successful run |
