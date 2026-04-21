import logging
from contextlib import contextmanager

from rich.logging import RichHandler

_SUPPRESS_CONSOLE_LOGS = 0


class ProgressAwareRichHandler(RichHandler):
    def emit(self, record: logging.LogRecord) -> None:
        if _SUPPRESS_CONSOLE_LOGS and record.levelno < logging.ERROR:
            return
        super().emit(record)


@contextmanager
def suppress_console_logs():
    global _SUPPRESS_CONSOLE_LOGS
    _SUPPRESS_CONSOLE_LOGS += 1
    try:
        yield
    finally:
        _SUPPRESS_CONSOLE_LOGS -= 1


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取带有 rich 格式化的 logger"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = ProgressAwareRichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
