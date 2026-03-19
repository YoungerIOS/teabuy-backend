import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings


def _normalize_citycode(citycode: Any) -> str:
    if isinstance(citycode, list):
        return citycode[0] if citycode else ""
    if citycode is None:
        return ""
    return str(citycode)


def _normalize_node(node: dict) -> dict:
    children = node.get("districts", [])
    if not isinstance(children, list):
        children = []
    return {
        "adcode": str(node.get("adcode", "")),
        "name": str(node.get("name", "")),
        "center": str(node.get("center", "")),
        "level": str(node.get("level", "")),
        "citycode": _normalize_citycode(node.get("citycode")),
        "districts": [_normalize_node(child) for child in children if isinstance(child, dict)],
    }


@lru_cache(maxsize=1)
def load_china_area_tree() -> list[dict]:
    path = Path(settings.china_area_file)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        return []
    return [_normalize_node(node) for node in payload if isinstance(node, dict)]


def get_provinces() -> list[dict]:
    return load_china_area_tree()


def get_cities(province_adcode: str) -> list[dict]:
    for p in load_china_area_tree():
        if p["adcode"] == province_adcode:
            return p["districts"]
    return []


def get_districts(city_adcode: str) -> list[dict]:
    for p in load_china_area_tree():
        for c in p["districts"]:
            if c["adcode"] == city_adcode:
                return c["districts"]
    return []
