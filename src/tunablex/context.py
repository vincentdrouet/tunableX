from __future__ import annotations

import contextvars

from pydantic import BaseModel


class use_config:
    def __init__(self, cfg):
        self.cfg = cfg

    def __enter__(self):
        self._tok = _active_cfg.set(self.cfg)
        return self.cfg

    def __exit__(self, et, e, tb):
        _active_cfg.reset(self._tok)


# Active config context used at runtime for auto-injection
_active_cfg = contextvars.ContextVar[BaseModel]("tunablex_active_cfg", default=None)
