"""JSON 配置加载、验证和保存。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.core.types import (
    Gear,
    GearGate,
    GearMode,
    LayoutDefinition,
    LayoutID,
    ProfileParameters,
    ReverseUnlockMethod,
)


# 配置目录（相对于项目根目录）
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =============================================================================
# Layout 加载
# =============================================================================

def load_layouts() -> dict[LayoutID, LayoutDefinition]:
    """从 default_layouts.json 加载所有 H 档排布定义。"""
    path = _CONFIG_DIR / "default_layouts.json"
    raw = _load_json(path)
    layouts: dict[LayoutID, LayoutDefinition] = {}

    for layout_data in raw.get("layouts", {}).values():
        layout_id = LayoutID(layout_data["id"])
        gates = []
        for g in layout_data.get("gates", []):
            gates.append(GearGate(
                gear=Gear(g["gear"]),
                x=float(g["x"]),
                y=float(g["y"]),
                width=float(g.get("width", 0.08)),
                lockout_rule=g.get("lockout_rule"),
            ))
        layouts[layout_id] = LayoutDefinition(
            layout_id=layout_id,
            display_name=layout_data.get("display_name", layout_id.value),
            x_range=tuple(layout_data.get("x_range", [0.0, 1.0])),
            y_range=tuple(layout_data.get("y_range", [0.0, 1.0])),
            neutral_zone_y=tuple(layout_data.get("neutral_zone_y", [0.4, 0.6])),
            neutral_center_x=float(layout_data.get("neutral_center_x", 0.5)),
            gates=gates,
        )

    return layouts


# =============================================================================
# Profile 加载/保存
# =============================================================================

def get_default_parameters() -> ProfileParameters:
    """从 default_profile.json 加载工厂默认参数。"""
    path = _CONFIG_DIR / "default_profile.json"
    if not path.exists():
        return ProfileParameters()
    raw = _load_json(path)
    params_data = raw.get("parameters", {})
    return ProfileParameters(**{
        k: v for k, v in params_data.items()
        if k in ProfileParameters.__dataclass_fields__
    })


def load_profiles() -> dict[str, dict[str, Any]]:
    """从 profiles.json 加载所有用户配置。"""
    path = _CONFIG_DIR / "profiles.json"
    if not path.exists():
        return {}
    raw = _load_json(path)
    return raw.get("profiles", {})


def save_profiles(profiles: dict[str, dict[str, Any]]) -> None:
    """保存所有用户配置到 profiles.json。"""
    path = _CONFIG_DIR / "profiles.json"
    _save_json(path, {"profiles": profiles})


def get_active_profile_name() -> str:
    """获取当前激活的配置名称。"""
    path = _CONFIG_DIR / "profiles.json"
    if not path.exists():
        return "Default"
    raw = _load_json(path)
    return raw.get("active_profile", "Default")


def set_active_profile_name(name: str) -> None:
    """设置当前激活的配置名称。"""
    path = _CONFIG_DIR / "profiles.json"
    if path.exists():
        raw = _load_json(path)
    else:
        raw = {"profiles": {}}
    raw["active_profile"] = name
    _save_json(path, raw)


def parse_profile(data: dict[str, Any]) -> dict[str, Any]:
    """解析单个配置条目，返回 mode, layout_id, reverse_unlock_method, parameters。"""
    mode = GearMode(data.get("mode", "HPATTERN"))
    layout_id = None
    if data.get("layout_id"):
        layout_id = LayoutID(data["layout_id"])
    reverse_method = None
    if data.get("reverse_unlock_method"):
        reverse_method = ReverseUnlockMethod(data["reverse_unlock_method"])
    params_data = data.get("parameters", {})
    params = ProfileParameters(**{
        k: v for k, v in params_data.items()
        if k in ProfileParameters.__dataclass_fields__
    })
    return {
        "mode": mode,
        "layout_id": layout_id,
        "reverse_unlock_method": reverse_method,
        "parameters": params,
    }
