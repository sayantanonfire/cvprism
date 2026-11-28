"""JSON Schemas (draft 2020-12) are the single source of truth for every file format."""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

NAMES = ("card", "registry", "device", "profile", "role", "manifest")


@lru_cache(maxsize=None)
def schema(name: str) -> dict:
    if name not in NAMES:
        raise KeyError(name)
    return json.loads(resources.files(__package__).joinpath(f"{name}.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(schema(name), format_checker=FormatChecker())


def errors(name: str, obj: Any) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in _validator(name).iter_errors(obj)]


def validate(name: str, obj: Any) -> None:
    errs = errors(name, obj)
    if errs:
        raise ValueError(f"invalid {name}: " + "; ".join(errs))
