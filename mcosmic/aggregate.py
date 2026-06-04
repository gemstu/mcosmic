# -*- coding: utf-8 -*-
"""Esemenyek osszesitese dimenzionkent."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from mcosmic.categories import DIMENSIONS, Categories

SZEREP_KEZDEMENYEZES = {1}
SZEREP_VALASZADAS = {2, 3, 4, 6}

DIMENSION_TITLES = {
    "kontextus": "Kontextus",
    "partner": "Partner",
    "funkcio": "Funkci\u00f3",
    "szerep": "Szerep",
    "forma": "Forma",
}


def summarize_dimension(
    events: pd.DataFrame,
    dimension: str,
    label_col: str | None = None,
) -> pd.DataFrame:
    if dimension not in events.columns:
        return pd.DataFrame(columns=["kod", "cimke", "darab"])

    label_col = label_col or f"{dimension}_label"
    subset = events[[dimension]].dropna()
    if subset.empty:
        return pd.DataFrame(columns=["kod", "cimke", "darab"])

    counts = subset[dimension].value_counts().sort_values(ascending=False)
    rows = []
    for code, count in counts.items():
        code_int = int(code)
        label = ""
        if label_col in events.columns:
            match = events.loc[events[dimension] == code, label_col].dropna()
            if not match.empty:
                label = str(match.iloc[0])
        rows.append({"kod": code_int, "cimke": label or f"({code_int})", "darab": int(count)})

    return pd.DataFrame(rows)


def summarize_all(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {dim: summarize_dimension(events, dim) for dim in DIMENSIONS if dim in events.columns}


def crosstab_kontextus_funkcio(events: pd.DataFrame) -> pd.DataFrame:
    """Kontextus x funkcio esemenyszamok (kodok + cimkek + darab)."""
    if "kontextus" not in events.columns or "funkcio" not in events.columns:
        return pd.DataFrame(
            columns=["kontextus", "kontextus_cimke", "funkcio", "funkcio_cimke", "darab"]
        )

    cols = ["kontextus", "funkcio"]
    label_cols = ["kontextus_label", "funkcio_label"]
    use = [c for c in cols + label_cols if c in events.columns]
    subset = events[use].dropna(subset=cols)
    if subset.empty:
        return pd.DataFrame(
            columns=["kontextus", "kontextus_cimke", "funkcio", "funkcio_cimke", "darab"]
        )

    grouped = (
        subset.groupby(cols, as_index=False)
        .size()
        .rename(columns={"size": "darab"})
    )
    for dim, label_col in (("kontextus", "kontextus_label"), ("funkcio", "funkcio_label")):
        cimke_col = f"{dim}_cimke"
        if label_col in subset.columns:
            labels = (
                subset.dropna(subset=[dim])
                .drop_duplicates(subset=[dim])
                .set_index(dim)[label_col]
                .astype(str)
            )
            grouped[cimke_col] = grouped[dim].map(labels)
        else:
            grouped[cimke_col] = grouped[dim].astype(str)
    return grouped.sort_values(["kontextus", "funkcio"]).reset_index(drop=True)


def kontextus_funkcio_matrix(
    crosstab: pd.DataFrame,
    categories: Categories,
) -> pd.DataFrame:
    """Sorok = kontextus, oszlopok = funkcio, ertekek = esemenyszam (0 ha nincs)."""
    kontextus_map = categories.maps.get("kontextus", {})
    funkcio_map = categories.maps.get("funkcio", {})

    if crosstab.empty:
        return pd.DataFrame()

    kontextus_codes = sorted(kontextus_map.keys()) if kontextus_map else sorted(
        int(c) for c in crosstab["kontextus"].unique()
    )
    funkcio_codes = sorted(funkcio_map.keys()) if funkcio_map else sorted(
        int(c) for c in crosstab["funkcio"].unique()
    )

    def _row_label(code: int) -> str:
        row = crosstab[crosstab["kontextus"] == code]
        if not row.empty and "kontextus_cimke" in row.columns:
            return str(row.iloc[0]["kontextus_cimke"])
        return kontextus_map.get(code, str(code))

    def _col_label(code: int) -> str:
        row = crosstab[crosstab["funkcio"] == code]
        if not row.empty and "funkcio_cimke" in row.columns:
            return str(row.iloc[0]["funkcio_cimke"])
        return funkcio_map.get(code, str(code))

    lookup = {
        (int(r["kontextus"]), int(r["funkcio"])): int(r["darab"])
        for _, r in crosstab.iterrows()
    }

    rows = []
    for k in kontextus_codes:
        k_int = int(k)
        rows.append(
            {
                "kontextus": _row_label(k_int),
                **{_col_label(int(f)): lookup.get((k_int, int(f)), 0) for f in funkcio_codes},
            }
        )
    return pd.DataFrame(rows).set_index("kontextus")


def kontextus_funkcio_change_matrix(
    current_events: pd.DataFrame,
    previous_events: pd.DataFrame,
    categories: Categories,
) -> pd.DataFrame:
    """Sorok = kontextus, oszlopok = funkcio; cella = aktualis - korabbi esemenyszam."""
    cur = kontextus_funkcio_matrix(
        crosstab_kontextus_funkcio(current_events), categories
    )
    prev = kontextus_funkcio_matrix(
        crosstab_kontextus_funkcio(previous_events), categories
    )
    if cur.empty and prev.empty:
        return pd.DataFrame()

    all_index = list(dict.fromkeys(list(cur.index) + list(prev.index)))
    all_cols = list(dict.fromkeys(list(cur.columns) + list(prev.columns)))
    cur_a = cur.reindex(index=all_index, columns=all_cols, fill_value=0)
    prev_a = prev.reindex(index=all_index, columns=all_cols, fill_value=0)
    return cur_a.astype(int) - prev_a.astype(int)


@dataclass(frozen=True)
class KezdemenyezesValaszadasStats:
    kezdemenyezes_darab: int
    valaszadas_darab: int
    osszesen: int
    kezdemenyezes_szazalek: float
    valaszadas_szazalek: float
    kihagyott_darab: int


def summarize_kezdemenyezes_vs_valaszadas(events: pd.DataFrame) -> KezdemenyezesValaszadasStats | None:
    """Szerep 1 = kezdemenyezes; 2, 3, 4, 6 = valaszadas (5 kimarad)."""
    if "szerep" not in events.columns:
        return None

    subset = events["szerep"].dropna()
    if subset.empty:
        return None

    kezdemenyezes = int((subset == 1).sum())
    valaszadas = int(subset.isin(SZEREP_VALASZADAS).sum())
    osszesen = kezdemenyezes + valaszadas
    if osszesen == 0:
        return None

    kihagyott = int(len(subset) - osszesen)
    return KezdemenyezesValaszadasStats(
        kezdemenyezes_darab=kezdemenyezes,
        valaszadas_darab=valaszadas,
        osszesen=osszesen,
        kezdemenyezes_szazalek=100.0 * kezdemenyezes / osszesen,
        valaszadas_szazalek=100.0 * valaszadas / osszesen,
        kihagyott_darab=kihagyott,
    )
