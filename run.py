#!/usr/bin/env python3
"""
run.py - Minimal MLOps-style batch job.

Loads OHLCV data, computes a rolling mean on `close`, derives a binary
trading signal, and writes structured metrics + logs.

CLI:
    python run.py --input data.csv --config config.yaml \
                   --output metrics.json --log-file run.log
"""

import argparse
import json
import logging
import os
import sys
import time

import numpy as np
import pandas as pd
import yaml

REQUIRED_CONFIG_FIELDS = ["seed", "window", "version"]


def parse_args():
    parser = argparse.ArgumentParser(description="MLOps batch signal job")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--output", required=True, help="Path to output metrics JSON file")
    parser.add_argument("--log-file", required=True, help="Path to log file")
    return parser.parse_args()


def setup_logging(log_file_path):
    """Configure logging to both file and stdout."""
    logger = logging.getLogger("mlops_task")
    logger.setLevel(logging.INFO)
    logger.handlers = []  # avoid duplicate handlers on re-invocation

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_file_path, mode="w")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


def write_metrics(output_path, payload):
    """Write metrics JSON. Called for both success and error paths."""
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)


def load_and_validate_config(config_path, logger):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML structure in config: {e}")

    if not isinstance(config, dict):
        raise ValueError("Invalid config structure: expected a YAML mapping/object")

    missing = [field for field in REQUIRED_CONFIG_FIELDS if field not in config]
    if missing:
        raise ValueError(f"Config missing required field(s): {', '.join(missing)}")

    if not isinstance(config["seed"], int):
        raise ValueError("Config field 'seed' must be an integer")
    if not isinstance(config["window"], int) or config["window"] < 1:
        raise ValueError("Config field 'window' must be a positive integer")
    if not isinstance(config["version"], str):
        raise ValueError("Config field 'version' must be a string")

    logger.info(
        f"Config loaded + validated: seed={config['seed']}, "
        f"window={config['window']}, version={config['version']}"
    )
    return config


def load_and_validate_dataset(input_path, logger):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if os.path.getsize(input_path) == 0:
        raise ValueError("Input file is empty")

    try:
        df = pd.read_csv(input_path)
    except pd.errors.EmptyDataError:
        raise ValueError("Input file is empty or contains no parseable data")
    except pd.errors.ParserError as e:
        raise ValueError(f"Invalid CSV format: {e}")

    if df.empty:
        raise ValueError("Input file contains no rows")

    if "close" not in df.columns:
        raise ValueError("Required column 'close' not found in input data")

    if df["close"].isnull().all():
        raise ValueError("Column 'close' contains no valid data")

    logger.info(f"Rows loaded: {len(df)}")
    return df


def compute_rolling_mean_and_signal(df, window, logger):
    """
    Compute rolling mean on `close` and derive a binary signal.

    First (window - 1) rows will have NaN rolling mean (standard pandas
    behavior) and are excluded from signal_rate calculation, but are still
    written to output with signal = 0 by convention (documented in README).
    """
    df = df.copy()
    df["rolling_mean"] = df["close"].rolling(window=window, min_periods=window).mean()
    logger.info(f"Rolling mean computed with window={window}")

    df["signal"] = np.where(df["close"] > df["rolling_mean"], 1, 0)
    # Rows without a valid rolling mean (NaN) get signal = 0 and are excluded
    # from signal_rate below, per the "allow NaNs, exclude from signal
    # computation" approach specified in the assessment.
    logger.info("Signal generation complete")

    return df


def main():
    args = parse_args()
    logger = setup_logging(args.log_file)
    start_time = time.perf_counter()

    logger.info("Job start")

    try:
        config = load_and_validate_config(args.config, logger)
        np.random.seed(config["seed"])

        df = load_and_validate_dataset(args.input, logger)
        df = compute_rolling_mean_and_signal(df, config["window"], logger)

        valid_signal_df = df.dropna(subset=["rolling_mean"])
        rows_processed = len(df)
        signal_rate = float(valid_signal_df["signal"].mean()) if len(valid_signal_df) > 0 else 0.0

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        metrics = {
            "version": config["version"],
            "rows_processed": rows_processed,
            "metric": "signal_rate",
            "value": round(signal_rate, 4),
            "latency_ms": latency_ms,
            "seed": config["seed"],
            "status": "success",
        }

        write_metrics(args.output, metrics)

        logger.info(
            f"Metrics summary: rows_processed={rows_processed}, "
            f"signal_rate={metrics['value']}, latency_ms={latency_ms}"
        )
        logger.info("Job end | status=success")

        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    except Exception as e:
        logger.exception(f"Job failed: {e}")

        error_metrics = {
            "version": "v1",
            "status": "error",
            "error_message": str(e),
        }

        try:
            write_metrics(args.output, error_metrics)
        except Exception as write_err:
            logger.error(f"Failed to write error metrics file: {write_err}")

        logger.info("Job end | status=error")

        print(json.dumps(error_metrics, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
