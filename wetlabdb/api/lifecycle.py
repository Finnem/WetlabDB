"""Application startup/shutdown hooks."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

_log = logging.getLogger("wetlabdb.lifecycle")


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("wetlabdb.access").setLevel(logging.INFO)
    logging.getLogger("wetlabdb.lifecycle").setLevel(logging.INFO)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    configure_logging()
    settings = app.state.settings
    _log.info(
        '{"event":"startup","mode":"%s"}',
        settings.mode,
    )
    try:
        yield
    finally:
        client = getattr(app.state, "client", None)
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                _log.warning('{"event":"shutdown.error","detail":"%s"}', str(exc))
        _log.info('{"event":"shutdown"}')


__all__ = ["app_lifespan", "configure_logging"]
