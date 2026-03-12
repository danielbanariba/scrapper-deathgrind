#!/usr/bin/env python3
"""
Sistema de logging centralizado para el scraper de DeathGrind.club
"""

import logging
import sys
import threading
from contextlib import contextmanager


_thread_local = threading.local()


def _get_log_context():
    return getattr(_thread_local, "log_context", "")


@contextmanager
def log_context(label):
    previous = _get_log_context()
    if label:
        _thread_local.log_context = f"[{label}] "
    else:
        _thread_local.log_context = ""
    try:
        yield
    finally:
        _thread_local.log_context = previous


class ContextFilter(logging.Filter):
    """Inyecta contexto por thread en cada línea de log."""

    def filter(self, record):
        record.log_context = _get_log_context()
        return True


class EmojiFormatter(logging.Formatter):
    """Formatter que usa los emojis existentes del proyecto como prefijo"""

    LEVEL_PREFIXES = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️ ",
        logging.WARNING: "⚠️ ",
        logging.ERROR: "❌",
        logging.CRITICAL: "💀",
    }

    def format(self, record):
        prefix = self.LEVEL_PREFIXES.get(record.levelno, "")
        record.emoji = prefix
        return super().format(record)


def setup_logger(name, verbose=True):
    """
    Configura y retorna un logger con formato consistente.

    Args:
        name: Nombre del logger (normalmente __name__ del módulo)
        verbose: Si True usa DEBUG, si False usa INFO

    Returns:
        logging.Logger configurado
    """
    logger = logging.getLogger(name)

    # Evitar duplicar handlers si se llama múltiples veces
    if logger.handlers:
        return logger

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    handler.addFilter(ContextFilter())

    formatter = EmojiFormatter("%(emoji)s %(log_context)s%(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger
