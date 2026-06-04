# -*- coding: utf-8 -*-
"""M-COSMIC CSV es Excel beolvasasa pandas DataFrame-be."""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

CODE_COLUMNS = ("kontextus", "partner", "funkcio", "szerep", "forma")
ENCODINGS = ("utf-8", "utf-8-sig", "cp1250", "latin-1")
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass
class SurveyResult:
    """Egy M-COSMIC felmeres feldolgozott eredmenye."""

    title: str
    meta: dict[str, str]
    events: pd.DataFrame


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


def _normalize_header(cell: str) -> str | None:
    key = _fold(cell)
    mapping = {
        "kontextus": "kontextus",
        "partner": "partner",
        "funkcio": "funkcio",
        "szerep": "szerep",
        "forma": "forma",
        "jegyzet": "jegyzet",
    }
    return mapping.get(key)


def _is_excel_source(path: str | Path | None) -> bool:
    if path is None:
        return False
    return Path(path).suffix.lower() in EXCEL_SUFFIXES


def _df_as_strings(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna("").astype(str)


def _read_csv_table(source: str | Path | io.BytesIO) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            if isinstance(source, io.BytesIO):
                source.seek(0)
                return pd.read_csv(source, sep=";", header=None, encoding=encoding, dtype=str)
            return pd.read_csv(source, sep=";", header=None, encoding=encoding, dtype=str)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("A CSV fajl kodolasa nem olvashato.") from last_error


def _resolve_survey_sheet(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if "kateg" in _fold(name):
            continue
        preview = _df_as_strings(xl.parse(name, header=None))
        try:
            _find_header_row(preview)
            return name
        except ValueError:
            continue
    return xl.sheet_names[0]


def _read_excel_table(source: str | Path | io.BytesIO) -> pd.DataFrame:
    if isinstance(source, io.BytesIO):
        source.seek(0)
        xl = pd.ExcelFile(source)
    else:
        xl = pd.ExcelFile(source)
    sheet = _resolve_survey_sheet(xl)
    df = xl.parse(sheet, header=None, dtype=str)
    return _df_as_strings(df)


def _read_raw_table(source: str | Path | io.BytesIO) -> pd.DataFrame:
    if _is_excel_source(source if isinstance(source, (str, Path)) else None):
        return _read_excel_table(source)
    return _read_csv_table(source)


def _find_header_row(df: pd.DataFrame) -> int:
    for i in range(min(10, len(df))):
        row = df.iloc[i].tolist()
        normalized = {_normalize_header(c) for c in row if pd.notna(c)}
        if "kontextus" in normalized and "partner" in normalized:
            return i
    raise ValueError("Nem talalhato esemeny fejlecsor (kontextus, partner, ...).")


def _meta_field(cell: str) -> str | None:
    folded = _fold(cell.rstrip(":"))
    if "gyermek" in folded:
        return "gyermek"
    if "megfigyel" in folded:
        return "megfigyeo"
    if "datum" in folded or "idoszak" in folded:
        return "datum_idoszak"
    return None


def _parse_meta_row(row: pd.Series) -> dict[str, str]:
    meta: dict[str, str] = {"gyermek": "", "megfigyeo": "", "datum_idoszak": ""}
    cells = [str(c).strip() for c in row.tolist()]

    for i, cell in enumerate(cells):
        if not cell:
            continue
        field = _meta_field(cell)
        if not field:
            continue
        if ":" in cell:
            _, _, value = cell.partition(":")
            value = value.strip()
        else:
            value = ""
        if not value and i + 1 < len(cells):
            nxt = cells[i + 1].strip()
            if nxt and _meta_field(nxt) is None:
                value = nxt
        if value and not meta[field]:
            meta[field] = value
    return meta


def _parse_code(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        code = int(float(s))
    except ValueError:
        return None
    return code if code > 0 else None


def _parse_sorszam(cell: Any) -> int | None:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None
    digits = re.sub(r"\D", "", str(cell))
    return int(digits) if digits else None


def _row_has_codes(row: dict[str, Any]) -> bool:
    return any(row.get(col) is not None for col in CODE_COLUMNS)


def parse_file(path: str | Path) -> SurveyResult:
    """CSV vagy Excel felmeresi fajl beolvasasa."""
    return _parse_dataframe(_read_raw_table(path))


def parse_bytes(data: bytes, filename: str | None = None) -> SurveyResult:
    """Feltoltott CSV vagy Excel tartalom beolvasasa."""
    if _is_excel_source(filename):
        return _parse_dataframe(_read_excel_table(io.BytesIO(data)))
    return _parse_dataframe(_read_csv_table(io.BytesIO(data)))


def parse_csv(path: str | Path) -> SurveyResult:
    """CSV fajl beolvasasa."""
    return parse_file(path)


def parse_excel(path: str | Path) -> SurveyResult:
    """Excel felmeresi fajl beolvasasa."""
    return parse_file(path)


def parse_csv_bytes(data: bytes) -> SurveyResult:
    """Feltoltott CSV tartalom beolvasasa."""
    return parse_bytes(data, filename=".csv")


def _parse_dataframe(df: pd.DataFrame) -> SurveyResult:
    df = df.fillna("")
    title = str(df.iloc[0, 0]).strip() if len(df) > 0 else ""
    meta = _parse_meta_row(df.iloc[1]) if len(df) > 1 else {"gyermek": "", "megfigyeo": "", "datum_idoszak": ""}
    header_idx = _find_header_row(df)
    header_row = df.iloc[header_idx]
    col_map: dict[int, str] = {}
    for col_idx, cell in enumerate(header_row.tolist()):
        name = _normalize_header(cell)
        if name:
            col_map[col_idx] = name

    records: list[dict[str, Any]] = []
    for i in range(header_idx + 1, len(df)):
        row = df.iloc[i]
        record: dict[str, Any] = {"sorszam": _parse_sorszam(row.iloc[0])}
        for col_idx, name in col_map.items():
            if name == "jegyzet":
                record["jegyzet"] = str(row.iloc[col_idx]).strip() if col_idx < len(row) else ""
            elif name in CODE_COLUMNS:
                record[name] = _parse_code(row.iloc[col_idx] if col_idx < len(row) else None)
        if not _row_has_codes(record):
            continue
        if record["sorszam"] is None:
            record["sorszam"] = len(records) + 1
        records.append(record)

    events = pd.DataFrame(records)
    if events.empty:
        events = pd.DataFrame(columns=["sorszam", *CODE_COLUMNS, "jegyzet"])
    else:
        for col in CODE_COLUMNS:
            if col in events.columns:
                events[col] = events[col].astype("Int64")
        if "jegyzet" not in events.columns:
            events["jegyzet"] = ""
        events = events.sort_values("sorszam", na_position="last").reset_index(drop=True)

    return SurveyResult(title=title, meta=meta, events=events)
