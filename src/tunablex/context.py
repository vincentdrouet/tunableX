from __future__ import annotations
import contextvars

# Trace context to collect namespaces touched during a dry-run
_active_trace = contextvars.ContextVar("tunablex_trace", default=None)

class trace_tunables:
    def __init__(self, noop: bool = True):
        self.namespaces = set()
        self.noop = noop
    def __enter__(self):
        self._tok = _active_trace.set(self)
        return self
    def __exit__(self, et, e, tb):
        _active_trace.reset(self._tok)

# Active config context used at runtime for auto-injection
_active_cfg = contextvars.ContextVar("tunablex_active_cfg", default=None)

class use_config:
    def __init__(self, cfg):
        self.cfg = cfg
    def __enter__(self):
        self._tok = _active_cfg.set(self.cfg)
        return self.cfg
    def __exit__(self, et, e, tb):
        _active_cfg.reset(self._tok)
