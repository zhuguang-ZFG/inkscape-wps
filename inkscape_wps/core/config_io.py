"""配置读写：JSON + TOML（优先 tomllib / 兼容 Python 3.10 的 tomli）。"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .config import MachineConfig

def resolve_config_path(directory: Path) -> Path:
    """若目录下已有配置则沿用其路径；否则默认 ``machine_config.toml``。"""
    directory.mkdir(parents=True, exist_ok=True)
    toml_p = directory / "machine_config.toml"
    json_p = directory / "machine_config.json"
    if toml_p.is_file():
        return toml_p
    if json_p.is_file():
        return json_p
    return toml_p


def load_machine_config(directory: Path) -> Tuple[MachineConfig, Path]:
    path = resolve_config_path(directory)
    if not path.is_file():
        return MachineConfig(), path
    if path.suffix.lower() == ".toml":
        return MachineConfig.load_toml(path), path
    return MachineConfig.load_json(path), path


def save_machine_config(cfg: MachineConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".toml":
        cfg.save_toml(path)
    else:
        cfg.save_json(path)
