# -*- coding: utf-8 -*-
"""Plotly diagramok M-COSMIC osszesitesekhez."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from mcosmic.aggregate import DIMENSION_TITLES, KezdemenyezesValaszadasStats
from mcosmic.categories import DIMENSIONS, Categories

_COLOR_COMPARE_PREVIOUS = "rgba(255, 127, 14, 0.85)"
_COLOR_COMPARE_CURRENT = "rgba(31, 119, 180, 0.85)"
_COLOR_DELTA_ZERO = "rgba(160, 160, 160, 0.7)"


def bar_chart(summary: pd.DataFrame, title: str) -> go.Figure | None:
    if summary.empty or summary["darab"].sum() == 0:
        return None

    labels = summary.apply(
        lambda r: f"{r['cimke']} ({r['kod']})" if r["cimke"] else str(r["kod"]),
        axis=1,
    )
    fig = go.Figure(
        go.Bar(
            x=summary["darab"],
            y=labels,
            orientation="h",
            text=summary["darab"],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Esem\u00e9nysz\u00e1m",
        yaxis_title="",
        height=max(280, 44 * len(summary)),
        margin=dict(l=20, r=40, t=50, b=40),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def charts_for_summaries(summaries: dict[str, pd.DataFrame]) -> dict[str, go.Figure | None]:
    result: dict[str, go.Figure | None] = {}
    for dim, table in summaries.items():
        title = DIMENSION_TITLES.get(dim, dim)
        result[dim] = bar_chart(table, f"{title} szerinti eloszl\u00e1s")
    return result


def _funkcio_radar_series(
    summary: pd.DataFrame,
    categories: Categories,
) -> tuple[list[str], list[int]] | None:
    """Funkcio cimkek + esemenyszamok (ugyanaz a tengely mindket felmereshez)."""
    all_funkcio = categories.maps.get("funkcio", {})
    if not all_funkcio and (summary.empty or summary["darab"].sum() == 0):
        return None

    if all_funkcio:
        codes = sorted(all_funkcio.keys())
        counts_map: dict[int, int] = {}
        if not summary.empty:
            counts_map = {int(r["kod"]): int(r["darab"]) for _, r in summary.iterrows()}
        labels = [all_funkcio[c] for c in codes]
        values = [counts_map.get(c, 0) for c in codes]
    else:
        summary = summary.sort_values("kod")
        labels = summary["cimke"].astype(str).tolist()
        values = summary["darab"].astype(int).tolist()

    if not labels:
        return None
    return labels, values


def _radar_polar_layout(max_val: int) -> dict:
    return dict(
        radialaxis=dict(
            visible=True,
            range=[0, max(max_val * 1.15, 1)],
            tick0=0,
            dtick=1 if max_val <= 10 else None,
        ),
    )


def _add_radar_trace(
    fig: go.Figure,
    labels: list[str],
    values: list[int],
    *,
    name: str,
    line_color: str,
    fill_color: str,
) -> None:
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]
    fig.add_trace(
        go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            name=name,
            line=dict(color=line_color),
            fillcolor=fill_color,
        )
    )


def funkcio_radar_chart(
    summary: pd.DataFrame,
    categories: Categories,
) -> go.Figure | None:
    """Radar (pok) diagram a kommunikacios funkciok esemenyszamairol."""
    series = _funkcio_radar_series(summary, categories)
    if series is None:
        return None
    labels, values = series
    if sum(values) == 0:
        return None

    fig = go.Figure()
    _add_radar_trace(
        fig,
        labels,
        values,
        name="Esem\u00e9nysz\u00e1m",
        line_color="rgba(31, 119, 180, 1)",
        fill_color="rgba(31, 119, 180, 0.35)",
    )
    max_val = max(values) if values else 1
    fig.update_layout(
        title="Funkci\u00f3 \u2013 radar diagram (p\u00f3kdiagram)",
        polar=_radar_polar_layout(max_val),
        height=520,
        margin=dict(t=60, b=40, l=80, r=80),
        showlegend=False,
    )
    return fig


def funkcio_radar_comparison_chart(
    current_summary: pd.DataFrame,
    previous_summary: pd.DataFrame,
    categories: Categories,
    *,
    current_label: str,
    previous_label: str,
) -> go.Figure | None:
    """Ket felmeres funkci radarja egy diagramon."""
    current = _funkcio_radar_series(current_summary, categories)
    previous = _funkcio_radar_series(previous_summary, categories)
    if current is None and previous is None:
        return None

    if current is None:
        labels, _ = previous
        current = (labels, [0] * len(labels))
    elif previous is None:
        labels, _ = current
        previous = (labels, [0] * len(labels))

    cur_labels, cur_values = current
    prev_labels, prev_values = previous
    if cur_labels != prev_labels:
        prev_values = [
            prev_values[prev_labels.index(lb)] if lb in prev_labels else 0
            for lb in cur_labels
        ]

    if sum(cur_values) == 0 and sum(prev_values) == 0:
        return None

    fig = go.Figure()
    traces: list[tuple[list[int], str, str, str]] = []
    if sum(cur_values) > 0:
        traces.append(
            (
                cur_values,
                _short_legend_label(current_label, 40),
                "rgba(31, 119, 180, 1)",
                "rgba(31, 119, 180, 0.25)",
            )
        )
    if sum(prev_values) > 0:
        traces.append(
            (
                prev_values,
                _short_legend_label(previous_label, 40),
                "rgba(255, 127, 14, 1)",
                "rgba(255, 127, 14, 0.25)",
            )
        )
    if not traces:
        return None

    for values, name, line_c, fill_c in traces:
        _add_radar_trace(
            fig, cur_labels, values, name=name, line_color=line_c, fill_color=fill_c
        )

    max_val = max(max(cur_values), max(prev_values), 1)
    fig.update_layout(
        title="Funkci\u00f3 \u2013 radar \u00f6sszehasonl\u00edt\u00e1s (aktu\u00e1lis vs kor\u00e1bbi)",
        polar=_radar_polar_layout(max_val),
        height=560,
        margin=dict(t=60, b=40, l=80, r=80),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.12, x=0.5, xanchor="center"),
    )
    return fig


def _short_legend_label(text: str, max_len: int = 28) -> str:
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _summary_count_map(summary: pd.DataFrame) -> dict[int, int]:
    if summary.empty:
        return {}
    return {int(r["kod"]): int(r["darab"]) for _, r in summary.iterrows()}


def _cimke_for_code(
    code: int,
    summary: pd.DataFrame,
    dim_map: dict[int, str],
) -> str:
    if not summary.empty:
        match = summary.loc[summary["kod"] == code, "cimke"]
        if not match.empty:
            cimke = str(match.iloc[0]).strip()
            if cimke and cimke != f"({code})":
                return cimke
    return dim_map.get(code, str(code))


def _dimension_comparison_series(
    current_summary: pd.DataFrame,
    previous_summary: pd.DataFrame,
    categories: Categories,
    dimension: str,
) -> tuple[list[str], list[int], list[int]] | None:
    dim_map = categories.maps.get(dimension, {})
    cur_map = _summary_count_map(current_summary)
    prev_map = _summary_count_map(previous_summary)

    if dim_map:
        codes = sorted(dim_map.keys())
    else:
        codes = sorted(set(cur_map) | set(prev_map))
        if not codes:
            return None

    labels = []
    for code in codes:
        cimke = _cimke_for_code(code, current_summary, dim_map)
        if cimke == str(code) and code not in cur_map:
            cimke = _cimke_for_code(code, previous_summary, dim_map)
        short = _short_legend_label(cimke, 22)
        labels.append(f"{short} ({code})")

    before = [prev_map.get(c, 0) for c in codes]
    after = [cur_map.get(c, 0) for c in codes]
    if sum(before) == 0 and sum(after) == 0:
        return None
    return labels, before, after


def dimension_before_after_chart(
    current_summary: pd.DataFrame,
    previous_summary: pd.DataFrame,
    categories: Categories,
    dimension: str,
    *,
    previous_label: str,
    current_label: str,
) -> go.Figure | None:
    """Csoportositott oszlopok: korabbi vs aktualis dimenzio szerint."""
    series = _dimension_comparison_series(
        current_summary, previous_summary, categories, dimension
    )
    if series is None:
        return None

    labels, before, after = series
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=_short_legend_label(previous_label, 36),
            x=labels,
            y=before,
            text=before,
            textposition="outside",
            marker_color=_COLOR_COMPARE_PREVIOUS,
        )
    )
    fig.add_trace(
        go.Bar(
            name=_short_legend_label(current_label, 36),
            x=labels,
            y=after,
            text=after,
            textposition="outside",
            marker_color=_COLOR_COMPARE_CURRENT,
        )
    )
    title = DIMENSION_TITLES.get(dimension, dimension)
    n_labels = len(labels)
    bottom_margin = max(90, 40 + min(n_labels * 14, 120))
    fig.update_layout(
        title=dict(
            text=f"{title} \u2013 el\u0151tte / ut\u00e1na",
            x=0.5,
            xanchor="center",
            pad=dict(b=8),
        ),
        xaxis_title="",
        yaxis_title="Esem\u00e9nysz\u00e1m",
        barmode="group",
        height=max(340, 48 * n_labels + 100),
        margin=dict(t=88, b=bottom_margin, l=50, r=24),
        xaxis=dict(tickangle=-35, automargin=True),
        legend=dict(
            title=dict(text="F\u00e1jl"),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0.5,
            xanchor="center",
            tracegroupgap=12,
        ),
    )
    return fig


def interaction_totals_comparison_chart(
    previous_count: int,
    current_count: int,
    *,
    previous_label: str,
    current_label: str,
) -> go.Figure:
    """Osszes kodolt interakcio: korabbi vs aktualis."""
    x_cat = "\u00d6sszes k\u00f3dolt interakci\u00f3"
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=_short_legend_label(previous_label, 36),
            x=[x_cat],
            y=[previous_count],
            text=[previous_count],
            textposition="outside",
            marker_color=_COLOR_COMPARE_PREVIOUS,
        )
    )
    fig.add_trace(
        go.Bar(
            name=_short_legend_label(current_label, 36),
            x=[x_cat],
            y=[current_count],
            text=[current_count],
            textposition="outside",
            marker_color=_COLOR_COMPARE_CURRENT,
        )
    )
    fig.update_layout(
        title="\u00d6sszes\u00edtett interakci\u00f3sz\u00e1m \u2013 el\u0151tte / ut\u00e1na",
        yaxis_title="Esem\u00e9nysz\u00e1m",
        barmode="group",
        height=320,
        margin=dict(t=56, b=48, l=50, r=24),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
    )
    return fig


def charts_dimension_before_after(
    current_summaries: dict[str, pd.DataFrame],
    previous_summaries: dict[str, pd.DataFrame],
    categories: Categories,
    *,
    previous_label: str,
    current_label: str,
) -> dict[str, go.Figure | None]:
    result: dict[str, go.Figure | None] = {}
    for dim in DIMENSIONS:
        cur = current_summaries.get(dim, pd.DataFrame())
        prev = previous_summaries.get(dim, pd.DataFrame())
        result[dim] = dimension_before_after_chart(
            cur,
            prev,
            categories,
            dim,
            previous_label=previous_label,
            current_label=current_label,
        )
    return result


def _delta_bar_color(value: int) -> str:
    if value > 0:
        return _COLOR_COMPARE_CURRENT
    if value < 0:
        return _COLOR_COMPARE_PREVIOUS
    return _COLOR_DELTA_ZERO


def dimension_delta_chart(
    current_summary: pd.DataFrame,
    previous_summary: pd.DataFrame,
    categories: Categories,
    dimension: str,
    *,
    current_label: str,
    previous_label: str,
) -> go.Figure | None:
    """Kulonbsegdiagram: csak valtozas (aktualis - korabbi) dimenzio szerint."""
    series = _dimension_comparison_series(
        current_summary, previous_summary, categories, dimension
    )
    if series is None:
        return None

    labels, before, after = series
    delta = [int(a) - int(b) for a, b in zip(after, before)]
    no_change = all(d == 0 for d in delta)
    bar_colors = [_delta_bar_color(d) for d in delta]
    text = [f"{d:+d}" if d != 0 else "0" for d in delta]
    title = DIMENSION_TITLES.get(dimension, dimension)

    fig = go.Figure(
        go.Bar(
            x=delta,
            y=labels,
            orientation="h",
            text=text,
            textposition="outside",
            marker_color=bar_colors,
            hovertemplate=(
                "Kategoria: %{y}<br>"
                f"V\u00e1ltoz\u00e1s: %{{x:+d}}<br>"
                f"{previous_label}: %{{customdata[0]}}<br>"
                f"{current_label}: %{{customdata[1]}}<extra></extra>"
            ),
            customdata=list(zip(before, after)),
        )
    )
    fig.add_vline(x=0, line_width=1, line_color="rgba(80, 80, 80, 0.6)")
    n_labels = len(labels)
    title_layout: dict = dict(
        text=(
            f"{title} \u2013 k\u00fcl\u00f6nbs\u00e9g "
            f"({current_label} \u2212 {previous_label})"
        ),
        x=0.5,
        xanchor="center",
        pad=dict(b=8),
    )
    if no_change:
        title_layout["subtitle"] = dict(
            text="Nem volt v\u00e1ltoz\u00e1s.",
            font=dict(size=12, color="rgba(80, 80, 80, 1)"),
        )
    top_margin = 96 if no_change else 72
    fig.update_layout(
        title=title_layout,
        xaxis_title="V\u00e1ltoz\u00e1s (esem\u00e9nysz\u00e1m)",
        yaxis_title="",
        height=max(300, 44 * n_labels + 80),
        margin=dict(t=top_margin, b=48, l=20, r=48),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    return fig


def charts_dimension_delta(
    current_summaries: dict[str, pd.DataFrame],
    previous_summaries: dict[str, pd.DataFrame],
    categories: Categories,
    *,
    previous_label: str,
    current_label: str,
) -> dict[str, go.Figure | None]:
    result: dict[str, go.Figure | None] = {}
    for dim in DIMENSIONS:
        cur = current_summaries.get(dim, pd.DataFrame())
        prev = previous_summaries.get(dim, pd.DataFrame())
        result[dim] = dimension_delta_chart(
            cur,
            prev,
            categories,
            dim,
            previous_label=previous_label,
            current_label=current_label,
        )
    return result


def kontextus_funkcio_grouped_bar(
    crosstab: pd.DataFrame,
    categories: Categories,
) -> go.Figure | None:
    """Csoportositott oszlopdiagram: kontextus (x) x funkcio (szin/csoport)."""
    if crosstab.empty or crosstab["darab"].sum() == 0:
        return None

    kontextus_map = categories.maps.get("kontextus", {})
    funkcio_map = categories.maps.get("funkcio", {})

    kontextus_codes = sorted(kontextus_map.keys()) if kontextus_map else sorted(
        crosstab["kontextus"].unique()
    )
    funkcio_codes = sorted(funkcio_map.keys()) if funkcio_map else sorted(
        crosstab["funkcio"].unique()
    )

    def _label(dim: str, code: int, cimke_col: str) -> str:
        row = crosstab[crosstab[dim] == code]
        if not row.empty and cimke_col in row.columns:
            return str(row.iloc[0][cimke_col])
        maps = kontextus_map if dim == "kontextus" else funkcio_map
        return maps.get(int(code), str(code))

    x_labels = [_label("kontextus", int(k), "kontextus_cimke") for k in kontextus_codes]
    lookup = {
        (int(r["kontextus"]), int(r["funkcio"])): int(r["darab"])
        for _, r in crosstab.iterrows()
    }

    palette = qualitative.Plotly
    fig = go.Figure()
    color_idx = 0
    for fk in funkcio_codes:
        fk_int = int(fk)
        counts = [lookup.get((int(k), fk_int), 0) for k in kontextus_codes]
        if sum(counts) == 0:
            continue
        funkcio_label = funkcio_map.get(fk_int) or _label("funkcio", fk_int, "funkcio_cimke")
        fig.add_trace(
            go.Bar(
                name=_short_legend_label(funkcio_label),
                x=x_labels,
                y=counts,
                text=counts,
                textposition="outside",
                marker_color=palette[color_idx % len(palette)],
            )
        )
        color_idx += 1

    if not fig.data:
        return None

    n_legend = len(fig.data)
    legend_rows = max(1, (n_legend + 3) // 4)
    bottom_extra = 50 + legend_rows * 32

    fig.update_layout(
        title=dict(
            text="Kontextus szerinti kommunik\u00e1ci\u00f3 \u2013 funkci\u00f3k",
            x=0.5,
            xanchor="center",
            pad=dict(t=8, b=16),
        ),
        xaxis_title="Kontextus",
        yaxis_title="Esem\u00e9nysz\u00e1m",
        barmode="group",
        height=max(460, 200 + legend_rows * 32),
        margin=dict(t=72, b=bottom_extra, l=50, r=20),
        legend=dict(
            title=dict(text="Funkci\u00f3 (sz\u00ednek)"),
            orientation="h",
            yanchor="top",
            y=-0.18 - 0.1 * (legend_rows - 1),
            x=0.5,
            xanchor="center",
            tracegroupgap=10,
        ),
    )
    return fig


def kontextus_funkcio_heatmap(matrix: pd.DataFrame) -> go.Figure | None:
    """Hoterkep: kontextus (y) x funkcio (x), ertekek = esemenyszam."""
    if matrix.empty or matrix.sum().sum() == 0:
        return None

    z = matrix.astype(int).values
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=list(matrix.columns),
            y=list(matrix.index),
            text=z,
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorscale="Blues",
            showscale=True,
            colorbar=dict(title="Esem\u00e9nysz\u00e1m"),
            hovertemplate=(
                "Kontextus: %{y}<br>Funkci\u00f3: %{x}<br>"
                "Darab: %{z}<extra></extra>"
            ),
        )
    )
    n_rows = len(matrix.index)
    n_cols = len(matrix.columns)
    fig.update_layout(
        title=dict(
            text="Kontextus szerinti kommunik\u00e1ci\u00f3 \u2013 funkci\u00f3k (h\u0151t\u00e9rk\u00e9p)",
            x=0.5,
            xanchor="center",
            pad=dict(t=8, b=12),
        ),
        xaxis=dict(title="Funkci\u00f3", tickangle=-35),
        yaxis=dict(title="Kontextus", autorange="reversed"),
        height=max(320, 48 * n_rows + 120),
        width=max(600, 72 * n_cols + 160),
        margin=dict(t=64, b=120, l=140, r=40),
    )
    return fig


def kontextus_funkcio_change_heatmap(
    change_matrix: pd.DataFrame,
    *,
    current_label: str = "Aktu\u00e1lis",
    previous_label: str = "Kor\u00e1bbi",
) -> go.Figure | None:
    """Hoterkep: kontextus x funkcio, cella = valtozas (aktualis - korabbi)."""
    if change_matrix.empty:
        return None

    z = change_matrix.astype(int).values
    if z.size == 0:
        return None

    z_flat = z.ravel()
    max_abs = max(int(abs(z_flat).max()) if len(z_flat) else 0, 1)
    text = [[f"{int(v):+d}" if int(v) != 0 else "0" for v in row] for row in z]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=list(change_matrix.columns),
            y=list(change_matrix.index),
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorscale=[
                [0.0, _COLOR_COMPARE_PREVIOUS],
                [0.5, "#ffffff"],
                [1.0, _COLOR_COMPARE_CURRENT],
            ],
            zmid=0,
            zmin=-max_abs,
            zmax=max_abs,
            showscale=True,
            colorbar=dict(title="V\u00e1ltoz\u00e1s"),
            hovertemplate=(
                "Kontextus: %{y}<br>Funkci\u00f3: %{x}<br>"
                "V\u00e1ltoz\u00e1s: %{z:+d}<extra></extra>"
            ),
        )
    )
    n_rows = len(change_matrix.index)
    n_cols = len(change_matrix.columns)
    fig.update_layout(
        title=dict(
            text=(
                "Kontextus \u00d7 funkci\u00f3 \u2013 v\u00e1ltoz\u00e1s "
                f"({current_label} \u2212 {previous_label})"
            ),
            x=0.5,
            xanchor="center",
            pad=dict(t=8, b=12),
        ),
        xaxis=dict(title="Funkci\u00f3", tickangle=-35),
        yaxis=dict(title="Kontextus", autorange="reversed"),
        height=max(320, 48 * n_rows + 120),
        width=max(600, 72 * n_cols + 160),
        margin=dict(t=64, b=120, l=140, r=40),
    )
    return fig


def kezdemenyezes_valaszadas_100_bar(
    stats: KezdemenyezesValaszadasStats,
) -> go.Figure:
    """100%-os vizszintes savdiagram: kezdemenyezes (1) vs valaszadas (2,3,4,6)."""
    pct_k = stats.kezdemenyezes_szazalek
    pct_v = stats.valaszadas_szazalek
    text_k = f"{pct_k:.0f}% ({stats.kezdemenyezes_darab})"
    text_v = f"{pct_v:.0f}% ({stats.valaszadas_darab})"

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Kezdem\u00e9nyez\u00e9s (szerep 1)",
            y=[""],
            x=[pct_k],
            orientation="h",
            marker_color="rgba(55, 128, 191, 0.85)",
            text=[text_k],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=(
                "Kezdem\u00e9nyez\u00e9s<br>%{x:.1f}%%<br>"
                f"{stats.kezdemenyezes_darab} esem\u00e9ny<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            name="V\u00e1laszad\u00e1s (szerep 2, 3, 4, 6)",
            y=[""],
            x=[pct_v],
            orientation="h",
            marker_color="rgba(255, 127, 14, 0.85)",
            text=[text_v],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=(
                "V\u00e1laszad\u00e1s<br>%{x:.1f}%%<br>"
                f"{stats.valaszadas_darab} esem\u00e9ny<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=dict(
            text="Kezdem\u00e9nyez\u00e9s vs v\u00e1laszad\u00e1s",
            x=0.5,
            xanchor="center",
            pad=dict(t=8, b=12),
        ),
        barmode="stack",
        xaxis=dict(
            range=[0, 100],
            ticksuffix="%",
            title="Ar\u00e1ny",
            showgrid=True,
            gridcolor="rgba(0,0,0,0.08)",
        ),
        yaxis=dict(showticklabels=False),
        height=220,
        margin=dict(t=64, b=48, l=24, r=24),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.35,
            x=0.5,
            xanchor="center",
        ),
        showlegend=True,
    )
    return fig
