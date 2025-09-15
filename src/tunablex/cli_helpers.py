from __future__ import annotations
from typing import get_origin, get_args, Literal
from pydantic import BaseModel
from jsonargparse import ArgumentParser  # works with jsonargparse or argparse-compatible
from argparse import BooleanOptionalAction, SUPPRESS
from pathlib import Path
from .runtime import make_app_config_for, make_app_config_for_entry
from .io import load_structured_config


def _help_with_default(fld) -> str | None:
    desc = getattr(fld, "description", None)
    if fld.is_required():
        return f"{desc} (required)" if desc else "(required)"
    # field has a default
    default_val = fld.default
    # Normalize default representation
    if isinstance(default_val, bool):
        default_str = str(default_val).lower()
    elif isinstance(default_val, Path):
        default_str = str(default_val)
    else:
        default_str = repr(default_val)
    if desc:
        return f"{desc} (default: {default_str})"
    return f"(default: {default_str})"


def add_flags_from_model(parser: ArgumentParser, AppConfig) -> None:
    """Create flags like --section.field for each tunable in the AppConfig model.

    Parser defaults are SUPPRESS so we can detect presence via hasattr(args, dest).
    Actual defaults still come from the Pydantic model instance when building the config.
    """
    for section_name, section_field in AppConfig.model_fields.items():
        section_model = section_field.annotation
        if not (isinstance(section_model, type) and issubclass(section_model, BaseModel)):
            continue
        grp = parser.add_argument_group(section_name)
        for name, fld in section_model.model_fields.items():
            ann = fld.annotation
            help_text = _help_with_default(fld)
            flag = f"--{section_name}.{name}"
            dest = f"TX__{section_name}__{name}"
            if get_origin(ann) is Literal:
                grp.add_argument(flag, choices=[*get_args(ann)], dest=dest, help=help_text, default=SUPPRESS)
            elif ann is bool:
                grp.add_argument(flag, action=BooleanOptionalAction, dest=dest, help=help_text, default=SUPPRESS)
            elif ann in (int, float, str):
                grp.add_argument(flag, type=ann, dest=dest, help=help_text, default=SUPPRESS)
            elif ann is Path:
                grp.add_argument(flag, type=str, dest=dest, help=help_text, default=SUPPRESS)
            else:
                grp.add_argument(flag, type=str, dest=dest, help=help_text, default=SUPPRESS)  # fallback; validated later

def add_flags_by_app(parser: ArgumentParser, app: str):
    """Add flags for all tunables tagged with the given app and return the AppConfig model."""
    AppConfig = make_app_config_for(app)
    add_flags_from_model(parser, AppConfig)
    return AppConfig

def add_flags_by_entry(parser: ArgumentParser, entrypoint, *args, **kwargs) -> None:
    AppConfig = make_app_config_for_entry(entrypoint, *args, **kwargs)
    add_flags_from_model(parser, AppConfig)

# New helper: trace an entrypoint to discover all tunables it (transitively) uses and add flags.
# Returns the generated AppConfig so callers can avoid a second trace.

def add_flags_by_trace(parser: ArgumentParser, entrypoint, *args, **kwargs):
    AppConfig = make_app_config_for_entry(entrypoint, *args, **kwargs)
    add_flags_from_model(parser, AppConfig)
    return AppConfig

def deep_update(base: dict, extra: dict) -> dict:
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base

def collect_overrides(args, AppConfig) -> dict:
    out = {}
    for section_name, section_field in AppConfig.model_fields.items():
        section_model = section_field.annotation
        if not (isinstance(section_model, type) and issubclass(section_model, BaseModel)):
            continue
        for name in section_model.model_fields.keys():
            dest = f"TX__{section_name}__{name}"
            if hasattr(args, dest):  # present only if supplied (SUPPRESS otherwise)
                val = getattr(args, dest)
                if val is not None:
                    out.setdefault(section_name, {})[name] = val
    return out

def build_cfg_from_file_and_args(AppConfig, args, config_attr: str = "config") -> dict:
    cfg = AppConfig().model_dump(mode="json")
    path = getattr(args, config_attr, None)
    if path:
        cfg = deep_update(cfg, load_structured_config(path))
    overrides = collect_overrides(args, AppConfig)
    cfg = deep_update(cfg, overrides)
    return cfg
