import logging
import sys
from datetime import datetime

COLORS = {
    "DEBUG":    "\033[36m",
    "INFO":     "\033[32m",
    "WARNING":  "\033[33m",
    "ERROR":    "\033[31m",
    "CRITICAL": "\033[35m",
    "RESET":    "\033[0m",
    "DIM":      "\033[2m",
}


class Formatter(logging.Formatter):
    def format(self, record):
        color = COLORS.get(record.levelname, "")
        reset = COLORS["RESET"]
        now = datetime.now().strftime("%H:%M:%S")

        name = record.name
        parts = name.split(".")
        short = ".".join(parts[-2:]) if len(parts) >= 2 else name

        icons = {"DEBUG": ".", "INFO": "+", "WARNING": "!", "ERROR": "x", "CRITICAL": "X"}
        icon = icons.get(record.levelname, ".")

        prefix = f"{COLORS['DIM']}{now}{reset} {short:<22} {color}{icon} {record.levelname:<7}{reset}"
        msg = f"{color}{record.getMessage()}{reset}"

        line = f"{prefix}| {msg}"
        if record.exc_info and record.exc_info[1]:
            line += f"\n{COLORS['ERROR']}{self.formatException(record.exc_info)}{reset}"
        return line


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(Formatter())
        logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger
