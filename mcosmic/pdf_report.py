# -*- coding: utf-8 -*-
"""M-COSMIC jelentes PDF generalasa."""

from __future__ import annotations

# Verzio: 2 = osszehasonlitas a PDF-ben (comparison parameter)
PDF_REPORT_VERSION = 2

import io
import os
import warnings
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
    KeepTogether,
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


def _kaleido_version() -> tuple[int, str] | None:
    try:
        import kaleido

        ver = str(getattr(kaleido, "__version__", "0"))
        return int(ver.split(".")[0]), ver
    except ImportError:
        return None


def _configure_kaleido_runtime() -> None:
    """Kaleido 1.x: Chromium utvonal (Linux / ha Chrome telepitve)."""
    if _kaleido_version() is None or _kaleido_version()[0] != 1:
        return
    import shutil

    for binary in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(binary)
        if path:
            os.environ.setdefault("CHROMIUM_PATH", path)
            os.environ.setdefault("GOOGLE_CHROME_SHIM", path)
            break


def _ensure_kaleido_ready() -> None:
    info = _kaleido_version()
    if info is None:
        raise RuntimeError(
            "Hianyzik a kaleido csomag. Telepites a projekt mappaban:\n"
            "  pip install -r requirements.txt"
        )
    major, ver = info
    if major >= 1:
        raise RuntimeError(
            f"A telepitett kaleido ({ver}) Google Chrome-ot igenyel. "
            "Hasznalj helyette: pip install kaleido==0.2.1"
        )


def _fig_to_image(fig: go.Figure, width: int = 900, height: int = 500) -> io.BytesIO:
    import plotly.io as pio

    _ensure_kaleido_ready()
    _configure_kaleido_runtime()
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            pio.write_image(fig, buf, format="png", width=width, height=height, scale=2)
        except Exception as exc:
            msg = str(exc).lower()
            if "chrome" in msg or "chromium" in msg or "plotly_get_chrome" in msg:
                raise RuntimeError(
                    "A diagramok PNG exportjahoz kaleido 0.2.1 kell (Chrome nelkul). "
                    "Telepites: pip install kaleido==0.2.1"
                ) from exc
            raise RuntimeError(f"Diagram export hiba: {exc}") from exc
    buf.seek(0)
    return buf


def _escape_xml(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _df_to_table(
    df: pd.DataFrame,
    font_name: str,
    page_width: float | None = None,
    col_widths: list[float] | None = None,
    font_size: int = 8,
) -> Table:
    """Táblázat; page_width megadásakor oszlopok az oldal szélességéhez igazítva."""
    n_cols = len(df.columns)
    if n_cols == 0:
        return Table([[]])

    if col_widths is None and page_width is not None:
        if n_cols == 1:
            col_widths = [page_width]
        else:
            first_ratio = 0.28 if n_cols > 5 else 0.32
            first_w = page_width * first_ratio
            rest_w = (page_width - first_w) / (n_cols - 1)
            col_widths = [first_w] + [rest_w] * (n_cols - 1)
        if n_cols > 6:
            font_size = 6
        elif n_cols > 4:
            font_size = 7

    header_style = ParagraphStyle(
        "TblHead",
        fontName=font_name,
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TblCell",
        fontName=font_name,
        fontSize=font_size,
        leading=font_size + 2,
    )

    def _cell(text: object, *, header: bool = False) -> Paragraph:
        style = header_style if header else cell_style
        return Paragraph(_escape_xml(text), style)

    data = [[_cell(c, header=True) for c in df.columns]]
    for row in df.values.tolist():
        data.append([_cell(v) for v in row])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _add_block(story: list[Any], flowables: list[Any]) -> None:
    """Cím + ábra/táblázat egy oldalon maradjon."""
    story.append(KeepTogether(flowables))


def _clone_figure(fig: go.Figure) -> go.Figure:
    return go.Figure(fig.to_dict())


def _prepare_heatmap_for_pdf(fig: go.Figure) -> go.Figure:
    """Hoterkep: extra margok PDF exportra (dolt x feliratok eleje)."""
    out = _clone_figure(fig)
    if not out.data:
        return out

    x_labels = list(out.data[0].x) if out.data[0].x is not None else []
    y_labels = list(out.data[0].y) if out.data[0].y is not None else []
    max_x_len = max((len(str(x)) for x in x_labels), default=10)
    max_y_len = max((len(str(y)) for y in y_labels), default=10)
    n_cols = max(len(x_labels), 1)
    n_rows = max(len(y_labels), 1)

    bottom = int(max(220, min(400, 130 + 10 * max_x_len)))
    left = int(max(200, min(320, 130 + 7 * max_y_len)))
    right = int(max(out.layout.margin.r or 40, 110))
    top = int(out.layout.margin.t or 72)
    export_w = max(1000, 56 * n_cols + left + right + 60)
    export_h = max(int(out.layout.height or 360), 52 * n_rows + top + bottom)

    out.update_layout(
        width=export_w,
        height=export_h,
        margin=dict(l=left, r=right, t=top, b=bottom),
        xaxis=dict(
            title="Funkci\u00f3",
            tickangle=-35,
            automargin=True,
        ),
        yaxis=dict(title="Kontextus", autorange="reversed", automargin=True),
    )
    return out


def _prepare_horizontal_bar_for_pdf(fig: go.Figure) -> go.Figure:
    """Vizszintes savdiagram: bal margó, hogy a kategórianevek látszódjanak a PDF-ben."""
    out = _clone_figure(fig)
    if not out.data:
        return out

    y_labels = list(out.data[0].y) if out.data[0].y is not None else []
    n_bars = max(len(y_labels), 1)
    max_len = max((len(str(y)) for y in y_labels), default=12)
    left_margin = int(max(140, min(340, 9 * max_len + 48)))
    top_m = int(out.layout.margin.t or 50)
    bottom_m = int(out.layout.margin.b or 48)
    export_w = max(1000, left_margin + 520)
    export_h = max(int(out.layout.height or 300), 44 * n_bars + top_m + bottom_m)

    out.update_layout(
        width=export_w,
        height=export_h,
        margin=dict(l=left_margin, r=72, t=top_m, b=bottom_m),
    )
    return out


def _chart_image(
    fig: go.Figure,
    doc: SimpleDocTemplate,
    *,
    width_px: int = 1000,
    height_px: int = 500,
    max_width: float | None = None,
    max_height: float | None = None,
) -> Image:
    """PDF kép – oldalarány megőrzése (ne nyújtsa szét vízszintesen)."""
    max_width = max_width or doc.width
    max_height = max_height or 13 * cm
    ratio = height_px / max(width_px, 1)
    img_w = min(24 * cm, max_width)
    img_h = img_w * ratio
    if img_h > max_height:
        img_h = max_height
        img_w = img_h / ratio
    return Image(_fig_to_image(fig, width_px, height_px), width=img_w, height=img_h)


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
    _ensure_kaleido_ready()
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
        story.append(_df_to_table(ev_df, font_name, page_width=doc.width))
        story.append(PageBreak())

        summaries = summarize_all(events)
        charts = charts_for_summaries(summaries)

        story.append(_section_title("\u00d6sszes\u00edt\u0151 diagramok", styles, font_name))
        for dim, fig in charts.items():
            if fig is None:
                continue
            fig_pdf = _prepare_horizontal_bar_for_pdf(fig)
            h_px = int(fig_pdf.layout.height or max(400, 44 * len(fig.data)))
            w_px = int(fig_pdf.layout.width or 1000)
            _add_block(
                story,
                [
                    _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name),
                    _chart_image(
                        fig_pdf,
                        doc,
                        width_px=w_px,
                        height_px=h_px,
                        max_width=22 * cm,
                        max_height=12 * cm,
                    ),
                ],
            )
            story.append(Spacer(1, 0.35 * cm))

        radar = funkcio_radar_chart(summaries.get("funkcio", pd.DataFrame()), categories)
        if radar is not None:
            _add_block(
                story,
                [
                    _body("<b>Funkci\u00f3 \u2013 radar diagram</b>", styles, font_name),
                    _chart_image(
                        radar,
                        doc,
                        width_px=900,
                        height_px=560,
                        max_width=22 * cm,
                        max_height=14 * cm,
                    ),
                ],
            )
            story.append(Spacer(1, 0.35 * cm))

        ctx_fn = crosstab_kontextus_funkcio(events)
        ctx_matrix = kontextus_funkcio_matrix(ctx_fn, categories)
        if not ctx_matrix.empty and ctx_matrix.sum().sum() > 0:
            story.append(PageBreak())
            mtx = ctx_matrix.reset_index().rename(columns={"kontextus": "Kontextus"})
            _add_block(
                story,
                [
                    _section_title(
                        "Kontextus szerinti kommunik\u00e1ci\u00f3 \u2013 funkci\u00f3k",
                        styles,
                        font_name,
                    ),
                    _body(
                        "T\u00e1bl\u00e1zat (sor = kontextus, oszlop = funkci\u00f3, cella = esem\u00e9nysz\u00e1m)",
                        styles,
                        font_name,
                    ),
                    _df_to_table(mtx, font_name, page_width=doc.width),
                ],
            )

            heatmap = kontextus_funkcio_heatmap(ctx_matrix)
            if heatmap is not None:
                story.append(Spacer(1, 0.25 * cm))
                heatmap_pdf = _prepare_heatmap_for_pdf(heatmap)
                h_px = int(heatmap_pdf.layout.height or 400)
                w_px = int(heatmap_pdf.layout.width or 1000)
                _add_block(
                    story,
                    [
                        _body("<b>H\u0151t\u00e9rk\u00e9p</b>", styles, font_name),
                        _chart_image(
                            heatmap_pdf,
                            doc,
                            width_px=w_px,
                            height_px=h_px,
                            max_width=doc.width,
                            max_height=16 * cm,
                        ),
                    ],
                )

            grouped = kontextus_funkcio_grouped_bar(ctx_fn, categories)
            if grouped is not None:
                story.append(Spacer(1, 0.25 * cm))
                _add_block(
                    story,
                    [
                        _body("<b>Csoportos\u00edtott oszlopdiagram</b>", styles, font_name),
                        _chart_image(
                            grouped,
                            doc,
                            width_px=1100,
                            height_px=520,
                            max_height=12 * cm,
                        ),
                    ],
                )

        szerep_stats = summarize_kezdemenyezes_vs_valaszadas(events)
        if szerep_stats is not None:
            story.append(Spacer(1, 0.25 * cm))
            szerep_fig = kezdemenyezes_valaszadas_100_bar(szerep_stats)
            _add_block(
                story,
                [
                    _section_title("Kezdem\u00e9nyez\u00e9s vs v\u00e1laszad\u00e1s", styles, font_name),
                    _body(_szerep_stats_text(szerep_stats), styles, font_name),
                    _chart_image(
                        szerep_fig,
                        doc,
                        width_px=900,
                        height_px=280,
                        max_width=22 * cm,
                        max_height=7 * cm,
                    ),
                ],
            )

        story.append(PageBreak())
        story.append(_section_title("\u00d6sszes\u00edt\u0151 t\u00e1bl\u00e1k", styles, font_name))
        for dim, table in summaries.items():
            if table.empty:
                continue
            tbl = table.rename(
                columns={"kod": "K\u00f3d", "cimke": "C\u00edmke", "darab": "Darab"}
            )
            _add_block(
                story,
                [
                    _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name),
                    _df_to_table(tbl, font_name, page_width=doc.width),
                ],
            )
            story.append(Spacer(1, 0.2 * cm))

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
                doc=doc,
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
    doc: SimpleDocTemplate,
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
    intro_blocks: list[Any] = [
        _section_title(
            "\u00d6sszehasonl\u00edt\u00e1s kor\u00e1bbi felm\u00e9r\u00e9ssel",
            styles,
            font_name,
        ),
        _body(
            f"<b>Aktu\u00e1lis:</b> {current_filename}<br/>"
            f"<b>Kor\u00e1bbi:</b> {compare_filename}",
            styles,
            font_name,
        ),
    ]
    for warning in validate_event_codes(prev_survey.events, categories):
        intro_blocks.append(
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
        intro_blocks.extend(
            [
                _body("<b>Funkci\u00f3 \u2013 radar \u00f6sszehasonl\u00edt\u00e1s</b>", styles, font_name),
                _chart_image(
                    comparison,
                    doc,
                    width_px=900,
                    height_px=560,
                    max_width=22 * cm,
                    max_height=14 * cm,
                ),
            ]
        )
    _add_block(story, intro_blocks)
    story.append(Spacer(1, 0.25 * cm))

    totals_fig = interaction_totals_comparison_chart(
        n_prev,
        n_curr,
        previous_label=previous_label,
        current_label=current_label,
    )
    _add_block(
        story,
        [
            _body("<b>\u00d6sszes\u00edtett interakci\u00f3k</b>", styles, font_name),
            _body(
                f"<b>{previous_label}:</b> {n_prev} esem\u00e9ny<br/>"
                f"<b>{current_label}:</b> {n_curr} esem\u00e9ny<br/>"
                f"<b>V\u00e1ltoz\u00e1s:</b> {n_curr - n_prev:+d}",
                styles,
                font_name,
            ),
            _chart_image(
                totals_fig,
                doc,
                width_px=900,
                height_px=320,
                max_width=22 * cm,
                max_height=8 * cm,
            ),
        ],
    )
    story.append(Spacer(1, 0.25 * cm))

    ctx_change = kontextus_funkcio_change_matrix(events, prev_events, categories)
    change_heatmap = kontextus_funkcio_change_heatmap(
        ctx_change,
        current_label=current_label,
        previous_label=previous_label,
    )
    if change_heatmap is not None:
        change_pdf = _prepare_heatmap_for_pdf(change_heatmap)
        h_px = int(change_pdf.layout.height or 400)
        w_px = int(change_pdf.layout.width or 1000)
        _add_block(
            story,
            [
                _body("<b>Kontextus \u00d7 funkci\u00f3 \u2013 v\u00e1ltoz\u00e1s</b>", styles, font_name),
                _body(
                    "Cella = aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m.",
                    styles,
                    font_name,
                ),
                _chart_image(
                    change_pdf,
                    doc,
                    width_px=w_px,
                    height_px=h_px,
                    max_width=doc.width,
                    max_height=16 * cm,
                ),
            ],
        )
        story.append(Spacer(1, 0.25 * cm))

    before_after = charts_dimension_before_after(
        summaries,
        prev_summaries,
        categories,
        previous_label=previous_label,
        current_label=current_label,
    )
    ba_header_done = False
    for dim in DIMENSIONS:
        fig = before_after.get(dim)
        if fig is None:
            continue
        fig_pdf = _prepare_horizontal_bar_for_pdf(fig)
        h_px = int(fig_pdf.layout.height or _fig_layout_height(fig, 400))
        w_px = int(fig_pdf.layout.width or 1000)
        block: list[Any] = []
        if not ba_header_done:
            block.append(
                _body("<b>Dimenzi\u00f3nk\u00e9nti el\u0151tte \u2013 ut\u00e1na</b>", styles, font_name)
            )
            ba_header_done = True
        block.extend(
            [
                _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name),
                _chart_image(
                    fig_pdf,
                    doc,
                    width_px=w_px,
                    height_px=h_px,
                    max_width=22 * cm,
                    max_height=14 * cm if h_px > 420 else 12 * cm,
                ),
            ]
        )
        _add_block(story, block)
        story.append(Spacer(1, 0.2 * cm))

    delta_charts = charts_dimension_delta(
        summaries,
        prev_summaries,
        categories,
        previous_label=previous_label,
        current_label=current_label,
    )
    delta_header_done = False
    for dim in DIMENSIONS:
        fig = delta_charts.get(dim)
        if fig is None:
            continue
        fig_pdf = _prepare_horizontal_bar_for_pdf(fig)
        h_px = int(fig_pdf.layout.height or _fig_layout_height(fig, 360))
        w_px = int(fig_pdf.layout.width or 1000)
        block = []
        if not delta_header_done:
            block.extend(
                [
                    _body(
                        "<b>Dimenzi\u00f3nk\u00e9nti k\u00fcl\u00f6nbs\u00e9g (delta)</b>",
                        styles,
                        font_name,
                    ),
                    _body(
                        "Csak a v\u00e1ltoz\u00e1s: aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m.",
                        styles,
                        font_name,
                    ),
                ]
            )
            delta_header_done = True
        block.extend(
            [
                _body(f"<b>{DIMENSION_TITLES.get(dim, dim)}</b>", styles, font_name),
                _chart_image(
                    fig_pdf,
                    doc,
                    width_px=w_px,
                    height_px=h_px,
                    max_width=22 * cm,
                    max_height=13 * cm if h_px > 400 else 12 * cm,
                ),
            ]
        )
        _add_block(story, block)
        story.append(Spacer(1, 0.2 * cm))


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
