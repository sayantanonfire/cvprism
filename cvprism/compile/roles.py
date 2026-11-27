"""Role profiles: vault/roles/<id>.yaml overrides packaged starters; `extends` inherits (SCHEMA.md)."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from .. import yamlio
from ..schemas import validate

DEFAULT_LIMITS = {"pages": 2, "bullets_per_position": 5, "skills_max": 24, "cards_to_llm": 60}


class RoleError(ValueError):
    pass


def starter_roles() -> list[str]:
    d = resources.files("cvprism.data").joinpath("roles")
    return sorted(p.name[:-5] for p in d.iterdir() if p.name.endswith(".yaml"))


def _raw(name: str, vault: Path | None) -> dict:
    if vault is not None:
        p = Path(vault) / "roles" / f"{name}.yaml"
        if p.is_file():
            return yamlio.load(p) or {}
    res = resources.files("cvprism.data").joinpath("roles", f"{name}.yaml")
    if res.is_file():
        import io

        from ruamel.yaml import YAML

        return yamlio.plain(YAML(typ="safe").load(io.StringIO(res.read_text(encoding="utf-8")))) or {}
    raise RoleError(f"No role '{name}'. Starters: {', '.join(starter_roles())}; or add {name}.yaml to vault/roles/.")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_role(name: str, vault: Path | None, _depth: int = 0) -> dict:
    if _depth > 5:
        raise RoleError("role 'extends' chain too deep")
    raw = _raw(name, vault)
    if raw.get("extends"):
        parent = load_role(raw["extends"], vault, _depth + 1)
        parent.pop("extends", None)
        raw = _merge(parent, raw)
    raw.setdefault("limits", {})
    raw["limits"] = {**DEFAULT_LIMITS, **raw["limits"]}
    raw.setdefault("outputs", ["pdf", "docx", "md"])
    try:
        validate("role", raw)
    except ValueError as e:
        raise RoleError(str(e)) from e
    return raw
