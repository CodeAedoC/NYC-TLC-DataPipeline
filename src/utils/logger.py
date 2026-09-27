"""
src/utils/logger.py
Shared logger for the TLC pipeline.
All stages call get_logger() — never instantiate their own logger.
Setup is called once in main.py via setup_logger().
"""
import logging
import os
import sys


def setup_logger(log_level: str = "INFO") -> logging.Logger:
    """
    Configure the tlc_pipeline logger with file + console handlers.
    File: logs/pipeline.log (append mode — accumulates across runs).
    Console: stdout (mirrors all lines).
    Called once at pipeline start in main.py.
    """
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("tlc_pipeline")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated setup_logger() calls
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # File handler — append mode (tech_requirements.md §5)
    fh = logging.FileHandler("logs/pipeline.log", mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def get_logger() -> logging.Logger:
    """Return the shared tlc_pipeline logger instance."""
    return logging.getLogger("tlc_pipeline")
