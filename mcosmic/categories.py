# -*- coding: utf-8 -*-
"""Magyar kategoria-terkepek betoltese es esemenyek gazdagitasa."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

DIMENSIONS = ("kontextus", "partner", "funkcio", "szerep", "forma")
DEFAULT_CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "data" / "kategoriak.yaml"


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


@dataclass(frozen=True)
class Categories:
    maps: dict[str, dict[int, str]]

    def label(self, dimension: str, code: int | None) -> str | None:
        if code is None or pd.isna(code):
            return None
        return self.maps.get(dimension, {}).get(int(code))

    def unknown_codes(self, dimension: str, codes: pd.Series) -> list[int]:
        known = set(self.maps.get(dimension, {}))
        found: set[int] = set()
        for value in codes.dropna().unique():
            try:
                found.add(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(found - known)


def _normalize_maps(raw: dict[str, Any]) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    for dim, entries in raw.items():
        if str(dim).startswith("_"):
            continue
        dim_key = _fold(dim)
        if dim_key == "funkcio" or dim_key.startswith("funkc"):
            dim_key = "funkcio"
        if dim_key not in DIMENSIONS:
            continue
        mapping: dict[int, str] = {}
        if isinstance(entries, dict):
            for k, v in entries.items():
                mapping[int(k)] = str(v).strip()
        result[dim_key] = mapping
    for dim in DIMENSIONS:
        result.setdefault(dim, {})
    return result


def load_categories(path: str | Path | None = None) -> Categories:
    p = Path(path) if path else DEFAULT_CATEGORIES_PATH
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Categories(maps=_normalize_maps(raw))


def _resolve_category_sheet(path: Path) -> str:
    xl = pd.ExcelFile(path)
    for name in xl.sheet_names:
        if "kateg" in _fold(name):
            return name
    return xl.sheet_names[0]


def _header_to_dimension(header: str) -> str | None:
    folded = _fold(header)
    if folded.startswith("kontext"):
        return "kontextus"
    if "partner" in folded or "kommunikac" in folded:
        return "partner"
    if folded.startswith("funkc") or "funkcio" in folded:
        return "funkcio"
    if folded.startswith("szerep"):
        return "szerep"
    if folded.startswith("forma"):
        return "forma"
    return None


def _parse_wide_excel(df: pd.DataFrame) -> dict[str, dict[int, str]] | None:
    """Tobboszlopos tablazat: sor 0 = dimenzio fejlecek, parokban kod + cimke."""
    if df.shape[1] < 4 or df.shape[0] < 2:
        return None
    header_row = [_fold(c) if pd.notna(c) else "" for c in df.iloc[0]]
    dim_count = sum(1 for h in header_row if _header_to_dimension(h))
    if dim_count < 2:
        return None

    maps: dict[str, dict[int, str]] = {d: {} for d in DIMENSIONS}
    col = 0
    while col + 1 < df.shape[1]:
        header = str(df.iloc[0, col]) if pd.notna(df.iloc[0, col]) else ""
        dim = _header_to_dimension(header)
        if dim:
            for i in range(1, len(df)):
                raw_code = df.iloc[i, col]
                raw_label = df.iloc[i, col + 1]
                if pd.isna(raw_code) or not str(raw_code).strip():
                    continue
                try:
                    code = int(float(raw_code))
                except (TypeError, ValueError):
                    continue
                label = str(raw_label).strip() if pd.notna(raw_label) else ""
                if label:
                    maps[dim][code] = label
        col += 2
    if not any(maps.values()):
        return None
    return maps


def load_categories_from_excel(path: str | Path) -> Categories:
    path = Path(path)
    sheet = _resolve_category_sheet(path)
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    maps: dict[str, dict[int, str]] = {d: {} for d in DIMENSIONS}

    wide = _parse_wide_excel(df)
    if wide is not None:
        return Categories(maps=wide)

    if df.shape[1] >= 3:
        header_row = None
        for i in range(min(5, len(df))):
            row = [_fold(c) for c in df.iloc[i].tolist() if pd.notna(c)]
            if any("dimenz" in c or "kateg" in c for c in row):
                header_row = i
                break
        if header_row is not None:
            cols = [_fold(c) for c in df.iloc[header_row]]
            dim_col = next((i for i, c in enumerate(cols) if "dimenz" in c or "kateg" in c), 0)
            id_col = next((i for i, c in enumerate(cols) if c in ("id", "kod", "szam", "szam.")), 1)
            name_col = next(
                (i for i, c in enumerate(cols) if "nev" in c or "cimke" in c or "label" in c or "nev" in c),
                2,
            )
            for _, row in df.iloc[header_row + 1 :].iterrows():
                dim_raw = _fold(row.iloc[dim_col]) if pd.notna(row.iloc[dim_col]) else ""
                if dim_raw.startswith("funkc"):
                    dim = "funkcio"
                elif dim_raw in maps:
                    dim = dim_raw
                else:
                    continue
                try:
                    code = int(float(row.iloc[id_col]))
                except (TypeError, ValueError):
                    continue
                label = str(row.iloc[name_col]).strip() if pd.notna(row.iloc[name_col]) else ""
                if label:
                    maps[dim][code] = label
            return Categories(maps=maps)

    current_dim: str | None = None
    for _, row in df.iterrows():
        cells = [c for c in row.tolist() if pd.notna(c) and str(c).strip()]
        if not cells:
            continue
        first = _fold(cells[0])
        if first.startswith("funkc"):
            key = "funkcio"
        elif first in maps:
            key = first
        else:
            key = None
        if key and len(cells) == 1:
            current_dim = key
            continue
        if current_dim and len(cells) >= 2:
            try:
                code = int(float(cells[0]))
                label = str(cells[1]).strip()
                maps[current_dim][code] = label
            except (TypeError, ValueError):
                if key:
                    current_dim = key

    return Categories(maps=maps)


def enrich_events(events: pd.DataFrame, categories: Categories) -> pd.DataFrame:
    out = events.copy()
    for dim in DIMENSIONS:
        if dim not in out.columns:
            continue
        out[f"{dim}_label"] = out[dim].apply(lambda c: categories.label(dim, c))
    return out


def validate_event_codes(events: pd.DataFrame, categories: Categories) -> list[str]:
    dim_names = {
        "kontextus": "Kontextus",
        "partner": "Partner",
        "funkcio": "Funkci\u00f3",
        "szerep": "Szerep",
        "forma": "Forma",
    }
    warnings: list[str] = []
    for dim in DIMENSIONS:
        if dim not in events.columns:
            continue
        unknown = categories.unknown_codes(dim, events[dim])
        if unknown:
            warnings.append(
                f"{dim_names[dim]}: ismeretlen k\u00f3d(ok): {', '.join(str(u) for u in unknown)}"
            )
    return warnings
