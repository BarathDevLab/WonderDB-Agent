import logging
import os
import sys

# Configure basic logging structure
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger instance."""
    return logging.getLogger(name)
