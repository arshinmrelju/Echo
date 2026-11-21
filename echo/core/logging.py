import logging
import re
import sys

# Pattern to redact common secret tokens and keys
SECRET_PATTERNS = [
    (
        re.compile(
            r"(?i)(api[-_]?key|secret|password|bearer|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"
        ),
        r"\1: [REDACTED]",
    ),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED]"),
    (re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"), "[REDACTED]"),
]


class SecretScrubberFormatter(logging.Formatter):
    """Custom formatter that automatically scrubs sensitive credentials from logs."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        scrubbed = original
        for pattern, replacement in SECRET_PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)
        return scrubbed


def setup_logging(debug: bool = False) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger("echo")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = SecretScrubberFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

