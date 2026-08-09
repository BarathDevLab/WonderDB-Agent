import logging


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger instance."""

    return logging.getLogger(name)
