from __future__ import annotations
from typing import get_origin, get_args, Literal
from pydantic import BaseModel
from jsonargparse import ArgumentParser  # works with jsonargparse or argparse-compatible
from .runtime import make_app_config_for, make_app_config_for_entry
from .io import load_structured_config

# Accepts yes/no/true/false/1/0/on/off/y/n (case-insensitive)
def _parse_bool(value: str) -> bool:
    v = str(value).strip().lower()
    if v in {"1","true","t","yes","y","on"}:
        return True
    if v in {"0","false","f","no","n","off"}:
        return False
    raise ValueError(f"invalid boolean: {value!r} (expected yes/no/true/false/1/0)")

def add_flags_from_model(parser: ArgumentParser, AppConfig) -> None:
    """Create flags like --section.field for each tunable in the AppConfig model."""
    for section_name, section_field in AppConfig.model_fields.items():
        section_model = section_field.annotation
        if not (isinstance(section_model, type) and issubclass(section_model, BaseModel)):
            continue
        grp = parser.add_argument_group(section_name)
        for name, fld in section_model.model_fields.items():
            ann = fld.annotation
            flag = f"--{section_name}.{name}"
            dest = f"TX__{section_name}__{name}"
            if get_origin(ann) is Literal:
                grp.add_argument(flag, choices=[*get_args(ann)], dest=dest)
            elif ann is bool:
                grp.add_argument(flag, type=_parse_bool, metavar="{yes|no}", dest=dest)
            elif ann in (int, float, str):
                grp.add_argument(flag, type=ann, dest=dest)
            else:
                grp.add_argument(flag, type=str, dest=dest)  # fallback; validated later

def add_flags_by_app(parser: ArgumentParser, app: str) -> None:
    AppConfig = make_app_config_for(app)
    add_flags_from_model(parser, AppConfig)

def add_flags_by_entry(parser: ArgumentParser, entrypoint, *args, **kwargs) -> None:
    AppConfig = make_app_config_for_entry(entrypoint, *args, **kwargs)
    add_flags_from_model(parser, AppConfig)

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
            if hasattr(args, dest):
                val = getattr(args, dest)
                if val is not None:
                    out.setdefault(section_name, {})[name] = val
    return out

def build_cfg_from_file_and_args(AppConfig, args, config_attr: str = "config") -> dict:
    cfg = AppConfig().model_dump()
    path = getattr(args, config_attr, None)
    if path:
        cfg = deep_update(cfg, load_structured_config(path))
    overrides = collect_overrides(args, AppConfig)
    cfg = deep_update(cfg, overrides)
    return cfg
