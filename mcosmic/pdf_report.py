# -*- coding: utf-8 -*-
"""M-COSMIC jelentes PDF generalasa."""

from __future__ import annotations

# Verzio: 2 = osszehasonlitas a PDF-ben (comparison parameter)
PDF_REPORT_VERSION = 2

import io
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from mcosmic.aggregate import (
    DIMENSION_TITLES,
    KezdemenyezesValaszadasStats,
    crosstab_kontextus_funkcio,
    kontextus_funkcio_change_matrix,
    kontextus_funkcio_matrix,
    summarize_all,
    summarize_kezdemenyezes_vs_valaszadas,
)
from mcosmic.categories import DIMENSIONS, Categories, enrich_events, validate_event_codes
from mcosmic.loader import SurveyResult, parse_bytes
from mcosmic.viz import (
    charts_dimension_before_after,
    charts_dimension_delta,
    charts_for_summaries,
    funkcio_radar_chart,
    funkcio_radar_comparison_chart,
    interaction_totals_comparison_chart,
    kezdemenyezes_valaszadas_100_bar,
    kontextus_funkcio_change_heatmap,
    kontextus_funkcio_grouped_bar,
    kontextus_funkcio_heatmap,
)

PDF_DISPLAY_COLUMNS = [
    "sorszam",
    "kontextus_label",
    "partner_label",
    "funkcio_label",
    "szerep_label",
    "forma_label",
    "jegyzet",
]

_FONT_NAME = "MCosmicFont"
_FONT_REGISTERED = False


def _font_candidates() -> list[Path]:
    """Betutipus-kereses: csomagolt font eloszor (Streamlit Cloud / Linux)."""
    package_dir = Path(__file__).resolve().parent
    bundled = package_dir / "fonts"
    return [
        bundled / "NotoSans-Regular.ttf",
        bundled / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf"),
        Path(os.environ.get("WINDIR", "")) / "Fonts" / "arial.ttf",
        Path(os.environ.get("WINDIR", "")) / "Fonts" / "calibri.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]


def _register_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_NAME

    for path in _font_candidates():
        if path.is_file():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(path)))
            _FONT_REGISTERED = True
            return _FONT_NAME

    raise RuntimeError(
        "Nem talalhato TTF betutipus a PDF-hez. "
        "Ellenorizd, hogy a mcosmic/fonts/NotoSans-Regular.ttf megvan a repoban."
    )


def _configure_kaleido_runtime() -> None:
    """Kaleido 1.x: Chromium utvonal Linuxon (pl. Streamlit Cloud)."""
    import shutil

    for binary in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(binary)
        if path:
            os.environ.setdefault("CHROMIUM_PATH", path)
            os.environ.setdefault("GOOGLE_CHROME_SHIM", path)
            break


def _fig_to_image(fig: go.Figure, width: int = 900, height: int = 500) -> io.BytesIO:
    import plotly.io as pio

    _configure_kaleido_runtime()
    buf = io.BytesIO()
    try:
        pio.write_image(fig, buf, format="png", width=width, height=height, scale=2)
    except Exception as exc:
        msg = str(exc).lower()
        if "chrome" in msg or "kaleido" in msg:
            raise RuntimeError(
                "A diagramok PNG exportjahoz kaleido 0.2.1 kell (Chrome nelkul), "
                "vagy Chromium a szerveren. "
                "Telepites: pip install kaleido==0.2.1"
            ) from exc
        raise
    buf.seek(0)
    return buf


def _df_to_table(
    df: pd.DataFrame,
    font_name: str,
    col_widths: list[float] | None = None,
) -> Table:
    header = [str(c) for c in df.columns]
    rows = [[str(v) for v in row] for row in df.values.tolist()]
    data = [header] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font_name, 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ]
        )
    )
    return table


def _section_title(text: str, styles: Any, font_name: str) -> Paragraph:
    style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        spaceAfter=8,
        spaceBefore=12,
    )
    return Paragraph(text, style)


def _stem_label(filename: str | None, fallback: str) -> str:
    if not filename:
        return fallback
    return filename.rsplit(".", 1)[0] if "." in filename else filename


def _fig_layout_height(fig: go.Figure, default: int = 500) -> int:
    h = fig.layout.height
    return int(h) if h is not None else default


def _body(text: str, styles: Any, font_name: str) -> Paragraph:
    style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=13,
    )
    return Paragraph(text.replace("\n", "<br/>"), style)


def build_report_pdf(
    survey: SurveyResult,
    events: pd.DataFrame,
    categories: Categories,
    source_filename: str,
    validation_warnings: list[str] | None = None,
    comparison: tuple[str, bytes] | None = None,
) -> bytes:
    """Teljes oldal tartalma PDF-ben (diagramokkal, tablazatokkal).

    comparison: (korabbi fajl neve, fajl bajtjai) osszehasonlitashoz.
    """
    compare_filename = comparison[0] if comparison else None
    compare_bytes = comparison[1] if comparison else None
    font_name = _register_font()
    styles = getSampleStyleSheet()
    page_size = landscape(A4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    story: list[Any] = []

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        spaceAfter=12,
    )
    story.append(Paragraph("M-COSMIC feldolgoz\u00e1s \u00e9s vizualiz\u00e1ci\u00f3", title_style))
    story.append(
        _body(f"<b>Forr\u00e1sf\u00e1jl:</b> {source_filename}", styles, font_name)
    )
    if survey.title:
        story.append(_body(survey.title, styles, font_name))

    story.append(Spacer(1, 0.3 * cm))
    story.append(_section_title("Alapadatok", styles, font_name))
    meta_lines = [
        f"<b>Gyermek:</b> {survey.meta.get('gyermek') or '\u2014'}",
        f"<b>Megfigyel\u0151:</b> {survey.meta.get('megfigyeo') or '\u2014'}",
        f"<b>D\u00e1tum / id\u0151szak:</b> {survey.meta.get('datum_idoszak') or '\u2014'}",
    ]
    for line in meta_lines:
        story.append(_body(line, styles, font_name))

    if validation_warnings:
        story.append(Spacer(1, 0.2 * cm))
        for w in validation_warnings:
            story.append(_body(f"<i>Figyelmeztet\u00e9s: {w}</i>", styles, font_name))

    n_events = len(events)
    story.append(Spacer(1, 0.3 * cm))
    story.append(_section_title("K\u00f3dolt esem\u00e9nyek", styles, font_name))
    story.append(
        _body(
            f"\u00d6sszesen <b>{n_events}</b> k\u00f3dolt esem\u00e9ny "
            "(esem\u00e9nysz\u00e1m, nem perc/perc ar\u00e1ny).",
            styles,
            font_name,
        )
    )

    if n_events > 0:
        display_cols = [c for c in PDF_DISPLAY_COLUMNS if c in events.columns]
        ev_df = events[display_cols].copy()
        rename = {
            "sorszam": "Sorsz.",
            "kontextus_label": "Kontextus",
            "partner_label": "Partner",
            "funkcio_label": "Funkci\u00f3",
            "szerep_label": "Szerep",
            "forma_label": "Forma",
            "jegyzet": "Jegyzet",
        }
        ev_df = ev_df.rename(columns={k: v for k, v in rename.items() if k in ev_df.columns})
        story.append(_df_to_table(ev_df, font_name))
        story.append(PageBreak())

        summaries = summarize_all(events)
        charts = charts_for_summaries(summaries)

        story.append(_section_title("\u00d6sszes\u00edt\u0151 diagramok", styles, font_name))
        for dim, fig in charts.items():
            if fig is None:
                continue
            story.append(
                _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name)
            )
            img = _fig_to_image(fig, width=1000, height=max(400, 44 * len(fig.data)))
            story.append(Image(img, width=24 * cm, height=12 * cm))
            story.append(Spacer(1, 0.4 * cm))

        radar = funkcio_radar_chart(summaries.get("funkcio", pd.DataFrame()), categories)
        if radar is not None:
            story.append(_body("<b>Funkci\u00f3 \u2013 radar diagram</b>", styles, font_name))
            story.append(Image(_fig_to_image(radar, 700, 520), width=18 * cm, height=13 * cm))
            story.append(Spacer(1, 0.4 * cm))

        ctx_fn = crosstab_kontextus_funkcio(events)
        ctx_matrix = kontextus_funkcio_matrix(ctx_fn, categories)
        if not ctx_matrix.empty and ctx_matrix.sum().sum() > 0:
            story.append(PageBreak())
            story.append(
                _section_title(
                    "Kontextus szerinti kommunik\u00e1ci\u00f3 \u2013 funkci\u00f3k",
                    styles,
                    font_name,
                )
            )
            story.append(
                _body(
                    "T\u00e1bl\u00e1zat (sor = kontextus, oszlop = funkci\u00f3, cella = esem\u00e9nysz\u00e1m)",
                    styles,
                    font_name,
                )
            )
            mtx = ctx_matrix.reset_index().rename(columns={"kontextus": "Kontextus"})
            story.append(_df_to_table(mtx, font_name))

            heatmap = kontextus_funkcio_heatmap(ctx_matrix)
            if heatmap is not None:
                story.append(Spacer(1, 0.3 * cm))
                story.append(_body("<b>H\u0151t\u00e9rk\u00e9p</b>", styles, font_name))
                h = max(320, 48 * len(ctx_matrix.index) + 120)
                w = max(600, 72 * len(ctx_matrix.columns) + 160)
                story.append(
                    Image(_fig_to_image(heatmap, w, h), width=24 * cm, height=14 * cm)
                )

            grouped = kontextus_funkcio_grouped_bar(ctx_fn, categories)
            if grouped is not None:
                story.append(Spacer(1, 0.3 * cm))
                story.append(
                    _body("<b>Csoportos\u00edtott oszlopdiagram</b>", styles, font_name)
                )
                story.append(
                    Image(_fig_to_image(grouped, 1100, 520), width=24 * cm, height=12 * cm)
                )

        szerep_stats = summarize_kezdemenyezes_vs_valaszadas(events)
        if szerep_stats is not None:
            story.append(Spacer(1, 0.3 * cm))
            story.append(
                _section_title("Kezdem\u00e9nyez\u00e9s vs v\u00e1laszad\u00e1s", styles, font_name)
            )
            story.append(
                _body(
                    _szerep_stats_text(szerep_stats),
                    styles,
                    font_name,
                )
            )
            story.append(
                Image(
                    _fig_to_image(kezdemenyezes_valaszadas_100_bar(szerep_stats), 900, 280),
                    width=22 * cm,
                    height=7 * cm,
                )
            )

        story.append(PageBreak())
        story.append(_section_title("\u00d6sszes\u00edt\u0151 t\u00e1bl\u00e1k", styles, font_name))
        for dim, table in summaries.items():
            if table.empty:
                continue
            story.append(
                _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name)
            )
            tbl = table.rename(
                columns={"kod": "K\u00f3d", "cimke": "C\u00edmke", "darab": "Darab"}
            )
            story.append(_df_to_table(tbl, font_name))
            story.append(Spacer(1, 0.25 * cm))

        if compare_bytes and compare_filename:
            _append_comparison_to_story(
                story,
                events=events,
                summaries=summaries,
                categories=categories,
                compare_bytes=compare_bytes,
                compare_filename=compare_filename,
                current_filename=source_filename,
                styles=styles,
                font_name=font_name,
            )

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _append_comparison_to_story(
    story: list[Any],
    *,
    events: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
    categories: Categories,
    compare_bytes: bytes,
    compare_filename: str,
    current_filename: str,
    styles: Any,
    font_name: str,
) -> None:
    try:
        prev_survey = parse_bytes(compare_bytes, filename=compare_filename)
    except Exception as exc:
        story.append(PageBreak())
        story.append(
            _section_title(
                "\u00d6sszehasonl\u00edt\u00e1s kor\u00e1bbi felm\u00e9r\u00e9ssel",
                styles,
                font_name,
            )
        )
        story.append(
            _body(
                f"A kor\u00e1bbi f\u00e1jl feldolgoz\u00e1sa sikertelen: {exc}",
                styles,
                font_name,
            )
        )
        return

    prev_events = enrich_events(prev_survey.events, categories)
    prev_summaries = summarize_all(prev_events)
    n_prev = len(prev_events)
    n_curr = len(events)
    current_label = _stem_label(current_filename, "Aktu\u00e1lis")
    previous_label = _stem_label(compare_filename, "Kor\u00e1bbi")

    story.append(PageBreak())
    story.append(
        _section_title(
            "\u00d6sszehasonl\u00edt\u00e1s kor\u00e1bbi felm\u00e9r\u00e9ssel",
            styles,
            font_name,
        )
    )
    story.append(
        _body(
            f"<b>Aktu\u00e1lis:</b> {current_filename}<br/>"
            f"<b>Kor\u00e1bbi:</b> {compare_filename}",
            styles,
            font_name,
        )
    )
    for warning in validate_event_codes(prev_survey.events, categories):
        story.append(
            _body(f"<i>Kor\u00e1bbi felm\u00e9r\u00e9s: {warning}</i>", styles, font_name)
        )

    comparison = funkcio_radar_comparison_chart(
        summaries.get("funkcio", pd.DataFrame()),
        prev_summaries.get("funkcio", pd.DataFrame()),
        categories,
        current_label=current_label,
        previous_label=previous_label,
    )
    if comparison is not None:
        story.append(_body("<b>Funkci\u00f3 \u2013 radar \u00f6sszehasonl\u00edt\u00e1s</b>", styles, font_name))
        story.append(
            Image(
                _fig_to_image(comparison, 900, 560),
                width=22 * cm,
                height=14 * cm,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

    story.append(_body("<b>\u00d6sszes\u00edtett interakci\u00f3k</b>", styles, font_name))
    story.append(
        _body(
            f"<b>{previous_label}:</b> {n_prev} esem\u00e9ny<br/>"
            f"<b>{current_label}:</b> {n_curr} esem\u00e9ny<br/>"
            f"<b>V\u00e1ltoz\u00e1s:</b> {n_curr - n_prev:+d}",
            styles,
            font_name,
        )
    )
    totals_fig = interaction_totals_comparison_chart(
        n_prev,
        n_curr,
        previous_label=previous_label,
        current_label=current_label,
    )
    story.append(
        Image(
            _fig_to_image(totals_fig, 900, 320),
            width=22 * cm,
            height=8 * cm,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    ctx_change = kontextus_funkcio_change_matrix(events, prev_events, categories)
    change_heatmap = kontextus_funkcio_change_heatmap(
        ctx_change,
        current_label=current_label,
        previous_label=previous_label,
    )
    if change_heatmap is not None:
        story.append(
            _body("<b>Kontextus \u00d7 funkci\u00f3 \u2013 v\u00e1ltoz\u00e1s</b>", styles, font_name)
        )
        story.append(
            _body(
                "Cella = aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m.",
                styles,
                font_name,
            )
        )
        ch_rows = len(ctx_change.index)
        ch_cols = len(ctx_change.columns)
        h = max(320, 48 * ch_rows + 120)
        w = max(600, 72 * ch_cols + 160)
        story.append(
            Image(
                _fig_to_image(change_heatmap, w, h),
                width=24 * cm,
                height=14 * cm,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

    story.append(
        _body("<b>Dimenzi\u00f3nk\u00e9nti el\u0151tte \u2013 ut\u00e1na</b>", styles, font_name)
    )
    before_after = charts_dimension_before_after(
        summaries,
        prev_summaries,
        categories,
        previous_label=previous_label,
        current_label=current_label,
    )
    for dim in DIMENSIONS:
        fig = before_after.get(dim)
        if fig is None:
            continue
        story.append(
            _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name)
        )
        h = _fig_layout_height(fig, 400)
        img_h = 14 * cm if h > 420 else 12 * cm
        story.append(
            Image(
                _fig_to_image(fig, 1000, h),
                width=24 * cm,
                height=img_h,
            )
        )
        story.append(Spacer(1, 0.25 * cm))

    story.append(
        _body("<b>Dimenzi\u00f3nk\u00e9nti k\u00fcl\u00f6nbs\u00e9g (delta)</b>", styles, font_name)
    )
    story.append(
        _body(
            "Csak a v\u00e1ltoz\u00e1s: aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m.",
            styles,
            font_name,
        )
    )
    delta_charts = charts_dimension_delta(
        summaries,
        prev_summaries,
        categories,
        previous_label=previous_label,
        current_label=current_label,
    )
    for dim in DIMENSIONS:
        fig = delta_charts.get(dim)
        if fig is None:
            continue
        story.append(
            _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name)
        )
        h = _fig_layout_height(fig, 360)
        img_h = 12 * cm if h <= 400 else 13 * cm
        story.append(
            Image(
                _fig_to_image(fig, 1000, h),
                width=24 * cm,
                height=img_h,
            )
        )
        story.append(Spacer(1, 0.25 * cm))


def _szerep_stats_text(stats: KezdemenyezesValaszadasStats) -> str:
    extra = ""
    if stats.kihagyott_darab > 0:
        extra = (
            f" (A szerep 5: {stats.kihagyott_darab} esem\u00e9ny kimaradt az ar\u00e1nyl\u00e1sb\u00f3l.)"
        )
    return (
        f"Kezdem\u00e9nyez\u00e9s (szerep 1): <b>{stats.kezdemenyezes_szazalek:.0f}%</b> "
        f"({stats.kezdemenyezes_darab} esem\u00e9ny). "
        f"V\u00e1laszad\u00e1s (szerep 2, 3, 4, 6): <b>{stats.valaszadas_szazalek:.0f}%</b> "
        f"({stats.valaszadas_darab} esem\u00e9ny){extra}."
    )
