# -*- coding: utf-8 -*-
"""M-COSMIC Streamlit alkalmazas."""

from __future__ import annotations

import inspect

import pandas as pd
import streamlit as st

from mcosmic.aggregate import (
    DIMENSION_TITLES,
    crosstab_kontextus_funkcio,
    kontextus_funkcio_change_matrix,
    kontextus_funkcio_matrix,
    summarize_all,
    summarize_kezdemenyezes_vs_valaszadas,
)
from mcosmic.categories import (
    DIMENSIONS,
    Categories,
    enrich_events,
    load_categories,
    validate_event_codes,
)
from mcosmic.loader import SurveyResult, parse_bytes
from mcosmic import pdf_report
from mcosmic.pdf_report import PDF_REPORT_VERSION, build_report_pdf
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

DISPLAY_COLUMNS = [
    "sorszam",
    "kontextus",
    "kontextus_label",
    "partner",
    "partner_label",
    "funkcio",
    "funkcio_label",
    "szerep",
    "szerep_label",
    "forma",
    "forma_label",
    "jegyzet",
]


def _init_session_state() -> None:
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "uploaded_name" not in st.session_state:
        st.session_state.uploaded_name = None
    if "uploaded_bytes" not in st.session_state:
        st.session_state.uploaded_bytes = None
    if "compare_uploader_key" not in st.session_state:
        st.session_state.compare_uploader_key = 0
    if "compare_uploaded_name" not in st.session_state:
        st.session_state.compare_uploaded_name = None
    if "compare_uploaded_bytes" not in st.session_state:
        st.session_state.compare_uploaded_bytes = None


def _clear_compare_upload() -> None:
    st.session_state.compare_uploaded_name = None
    st.session_state.compare_uploaded_bytes = None
    st.session_state.compare_uploader_key += 1


def _clear_upload() -> None:
    st.session_state.uploaded_name = None
    st.session_state.uploaded_bytes = None
    st.session_state.uploader_key += 1
    _clear_compare_upload()


def _display_label(filename: str | None, fallback: str) -> str:
    if not filename:
        return fallback
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return stem


def _render_compare_upload_section() -> None:
    """Korabbi felmeres feltoltese osszehasonlitashoz."""
    st.markdown("##### \u00d6sszehasonl\u00edt\u00e1s kor\u00e1bbi felm\u00e9r\u00e9ssel")
    st.caption(
        "Opcion\u00e1lisan t\u00f6lts fel egy kor\u00e1bbi CSV vagy Excel felm\u00e9r\u00e9st "
        "(ugyanolyan form\u00e1tum). Megjelenik a funkci\u00f3 radar \u00f6sszehasonl\u00edt\u00e1s, "
        "az \u00f6sszes interakci\u00f3 kimutat\u00e1sa \u00e9s dimenzi\u00f3nk\u00e9nti el\u0151tte\u2013ut\u00e1na diagram."
    )

    if st.session_state.compare_uploaded_bytes:
        col_name, col_btn = st.columns([4, 2])
        with col_name:
            st.markdown(
                f"**Kor\u00e1bbi felm\u00e9r\u00e9s:** {st.session_state.compare_uploaded_name}"
            )
        with col_btn:
            if st.button(
                "Kor\u00e1bbi felm\u00e9r\u00e9s elt\u00e1vol\u00edt\u00e1sa",
                use_container_width=True,
                key="compare_clear_btn",
            ):
                _clear_compare_upload()
                st.rerun()
        return

    compare_file = st.file_uploader(
        "Kor\u00e1bbi felm\u00e9r\u00e9s felt\u00f6lt\u00e9se",
        type=["csv", "xlsx", "xlsm"],
        help="Ugyanaz a t\u00e1blaszerkezet, mint az aktu\u00e1lis f\u00e1jln\u00e1l.",
        key=f"compare_uploader_{st.session_state.compare_uploader_key}",
    )
    if compare_file is not None:
        st.session_state.compare_uploaded_name = compare_file.name
        st.session_state.compare_uploaded_bytes = compare_file.getvalue()
        st.rerun()


def _render_comparison_results(
    events: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
    categories: Categories,
) -> None:
    """Osszehasonlito diagramok - csak korabbi felmeres feltoltese utan."""
    compare_bytes = st.session_state.compare_uploaded_bytes
    compare_name = st.session_state.compare_uploaded_name
    if not compare_bytes or not compare_name:
        return

    funkcio_summary = summaries.get("funkcio", pd.DataFrame())
    current_label = _display_label(st.session_state.uploaded_name, "Aktu\u00e1lis")
    previous_label = _display_label(compare_name, "Kor\u00e1bbi")

    try:
        prev_survey = parse_bytes(compare_bytes, filename=compare_name)
        prev_events = enrich_events(prev_survey.events, categories)
        for warning in validate_event_codes(prev_survey.events, categories):
            st.warning(f"Kor\u00e1bbi felm\u00e9r\u00e9s: {warning}")
        prev_summaries = summarize_all(prev_events)
        n_prev = len(prev_events)
        n_curr = len(events)

        comparison = funkcio_radar_comparison_chart(
            funkcio_summary,
            prev_summaries.get("funkcio", pd.DataFrame()),
            categories,
            current_label=current_label,
            previous_label=previous_label,
        )
        if comparison is not None:
            st.plotly_chart(comparison, use_container_width=True)
        else:
            st.info(
                "Az \u00f6sszehasonl\u00edt\u00f3 radarhoz legal\u00e1bb az egyik "
                "felm\u00e9r\u00e9sben kell funkci\u00f3-adat."
            )

        st.markdown("##### \u00d6sszes\u00edtett interakci\u00f3k")
        m_prev, m_curr, m_delta = st.columns(3)
        m_prev.metric(previous_label, n_prev)
        m_curr.metric(current_label, n_curr)
        m_delta.metric(
            "V\u00e1ltoz\u00e1s",
            n_curr - n_prev,
            delta=f"{n_curr - n_prev:+d}",
        )
        st.plotly_chart(
            interaction_totals_comparison_chart(
                n_prev,
                n_curr,
                previous_label=previous_label,
                current_label=current_label,
            ),
            use_container_width=True,
        )

        ctx_change = kontextus_funkcio_change_matrix(events, prev_events, categories)
        change_heatmap = kontextus_funkcio_change_heatmap(
            ctx_change,
            current_label=current_label,
            previous_label=previous_label,
        )
        if change_heatmap is not None:
            st.markdown("##### Kontextus \u00d7 funkci\u00f3 \u2013 v\u00e1ltoz\u00e1s")
            st.caption(
                "Cella = aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m "
                "(k\u00e9k: t\u00f6bb, narancs: kevesebb a mostani m\u00e9r\u00e9sben)."
            )
            st.plotly_chart(change_heatmap, use_container_width=True)

        st.markdown("##### Dimenzi\u00f3nk\u00e9nti el\u0151tte \u2013 ut\u00e1na")
        before_after = charts_dimension_before_after(
            summaries,
            prev_summaries,
            categories,
            previous_label=previous_label,
            current_label=current_label,
        )
        ba_cols = st.columns(2)
        ba_idx = 0
        for dim in DIMENSIONS:
            fig = before_after.get(dim)
            if fig is None:
                continue
            with ba_cols[ba_idx % 2]:
                st.plotly_chart(fig, use_container_width=True)
            ba_idx += 1
        if ba_idx == 0:
            st.info("Nincs \u00f6sszehasonl\u00edthat\u00f3 adat egyik dimenzi\u00f3ban sem.")

        st.markdown("##### Dimenzi\u00f3nk\u00e9nti k\u00fcl\u00f6nbs\u00e9g (delta)")
        st.caption(
            "Csak a v\u00e1ltoz\u00e1s: aktu\u00e1lis \u2212 kor\u00e1bbi esem\u00e9nysz\u00e1m "
            "(k\u00e9k: t\u00f6bb, narancs: kevesebb)."
        )
        delta_charts = charts_dimension_delta(
            summaries,
            prev_summaries,
            categories,
            previous_label=previous_label,
            current_label=current_label,
        )
        d_cols = st.columns(2)
        d_idx = 0
        for dim in DIMENSIONS:
            fig = delta_charts.get(dim)
            if fig is None:
                continue
            with d_cols[d_idx % 2]:
                st.plotly_chart(fig, use_container_width=True)
            d_idx += 1
        if d_idx == 0:
            st.info(
                "Nincs \u00f6sszehasonl\u00edthat\u00f3 adat egyik dimenzi\u00f3ban sem "
                "(mindk\u00e9t m\u00e9r\u00e9sben \u00fcres)."
            )
    except Exception as exc:
        st.error(f"A kor\u00e1bbi f\u00e1jl feldolgoz\u00e1sa sikertelen: {exc}")


def _render_upload_section() -> tuple[str, bytes] | None:
    """Feltoltes vagy feldolgozott fajl neve + uj fajl gomb."""
    st.markdown("##### Felm\u00e9r\u00e9s (CSV vagy Excel)")

    if st.session_state.uploaded_bytes:
        col_name, col_btn = st.columns([4, 2])
        with col_name:
            st.markdown(
                f"**Felt\u00f6lt\u00f6tt f\u00e1jl:** {st.session_state.uploaded_name}"
            )
        with col_btn:
            if st.button(
                "\u00daj f\u00e1jl feldolgoz\u00e1sa",
                type="primary",
                use_container_width=True,
            ):
                _clear_upload()
                st.rerun()
        return st.session_state.uploaded_name, st.session_state.uploaded_bytes

    survey_file = st.file_uploader(
        "V\u00e1lassz f\u00e1jlt",
        type=["csv", "xlsx", "xlsm"],
        help="Pl. mcosmic_gyerek_1.csv vagy .xlsx. Nincs sorlimit.",
        label_visibility="collapsed",
        key=f"survey_uploader_{st.session_state.uploader_key}",
    )
    if survey_file is not None:
        st.session_state.uploaded_name = survey_file.name
        st.session_state.uploaded_bytes = survey_file.getvalue()
        st.rerun()

    return None


def _pdf_filename() -> str:
    base = st.session_state.uploaded_name or "mcosmic_jelentes"
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem}_mcosmic.pdf"


def _render_pdf_download(
    survey: SurveyResult,
    events: pd.DataFrame,
    categories: Categories,
) -> None:
    st.subheader("Jelent\u00e9s let\u00f6lt\u00e9se")
    warnings = validate_event_codes(survey.events, categories)
    try:
        pdf_kwargs: dict = {
            "survey": survey,
            "events": events,
            "categories": categories,
            "source_filename": st.session_state.uploaded_name or "felm\u00e9r\u00e9s",
            "validation_warnings": warnings,
        }
        cmp_name = st.session_state.compare_uploaded_name
        cmp_bytes = st.session_state.compare_uploaded_bytes
        sig = inspect.signature(build_report_pdf)
        if cmp_bytes and cmp_name:
            if "comparison" in sig.parameters:
                pdf_kwargs["comparison"] = (cmp_name, cmp_bytes)
            elif (
                "compare_filename" in sig.parameters
                and "compare_bytes" in sig.parameters
            ):
                pdf_kwargs["compare_filename"] = cmp_name
                pdf_kwargs["compare_bytes"] = cmp_bytes
            elif getattr(pdf_report, "PDF_REPORT_VERSION", 1) < PDF_REPORT_VERSION:
                st.warning(
                    "Az \u00f6sszehasonl\u00edt\u00e1s nem ker\u00fcl a PDF-be: "
                    "\u00e1ll\u00edtsd le a Streamlitet (Ctrl+C), majd ind\u00edtsd \u00fajra: "
                    "streamlit run app.py"
                )
        pdf_bytes = build_report_pdf(**pdf_kwargs)
    except Exception as exc:
        st.error(f"A PDF k\u00e9sz\u00edt\u00e9se sikertelen: {exc}")
        st.caption(
            "PDF diagramok: pip install kaleido==0.2.1 reportlab "
            "(Streamlit Cloud-on a requirements.txt-ben szerepel)."
        )
        return

    st.download_button(
        label="PDF jelent\u00e9s let\u00f6lt\u00e9se",
        data=pdf_bytes,
        file_name=_pdf_filename(),
        mime="application/pdf",
        type="primary",
    )


def _render_results(survey: SurveyResult) -> None:
    categories = load_categories()
    events = enrich_events(survey.events, categories)

    for warning in validate_event_codes(survey.events, categories):
        st.warning(warning)

    st.subheader("Alapadatok")
    m1, m2, m3 = st.columns(3)
    m1.metric("Gyermek", survey.meta.get("gyermek") or "\u2014")
    m2.metric("Megfigyel\u0151", survey.meta.get("megfigyeo") or "\u2014")
    m3.metric("D\u00e1tum / id\u0151szak", survey.meta.get("datum_idoszak") or "\u2014")
    if survey.title:
        st.caption(survey.title)

    n_events = len(events)
    st.subheader("K\u00f3dolt esem\u00e9nyek")
    st.markdown(
        f"**\u00d6sszesen {n_events} k\u00f3dolt esem\u00e9ny** "
        "(esem\u00e9nysz\u00e1m, nem perc/perc ar\u00e1ny)."
    )

    display_cols = [c for c in DISPLAY_COLUMNS if c in events.columns]
    st.dataframe(events[display_cols], use_container_width=True, hide_index=True)

    if n_events == 0:
        st.warning("Nincs k\u00f3dolt esem\u00e9ny a vizualiz\u00e1ci\u00f3hoz.")
        return

    st.subheader("\u00d6sszes\u00edt\u0151 diagramok")
    summaries = summarize_all(events)
    charts = charts_for_summaries(summaries)

    chart_cols = st.columns(2)
    idx = 0
    for dim, fig in charts.items():
        if fig is None:
            st.info(f"{DIMENSION_TITLES.get(dim, dim)}: nincs adat a diagramhoz.")
            continue
        with chart_cols[idx % 2]:
            st.plotly_chart(fig, use_container_width=True)
        idx += 1

    radar = funkcio_radar_chart(summaries.get("funkcio", pd.DataFrame()), categories)
    if radar is not None:
        st.plotly_chart(radar, use_container_width=True)
    else:
        st.info("Funkci\u00f3: nincs adat a radar diagramhoz.")

    ctx_fn = crosstab_kontextus_funkcio(events)
    ctx_matrix = kontextus_funkcio_matrix(ctx_fn, categories)

    st.markdown("##### Kontextus szerinti kommunik\u00e1ci\u00f3 \u2013 funkci\u00f3k")
    if ctx_matrix.empty or ctx_matrix.sum().sum() == 0:
        st.info("Kontextus \u00d7 funkci\u00f3: nincs adat a t\u00e1bl\u00e1zathoz \u00e9s diagramokhoz.")
    else:
        st.markdown("**T\u00e1bl\u00e1zat** (sor = kontextus, oszlop = funkci\u00f3, cella = esem\u00e9nysz\u00e1m)")
        st.dataframe(ctx_matrix, use_container_width=True)

        heatmap = kontextus_funkcio_heatmap(ctx_matrix)
        if heatmap is not None:
            st.plotly_chart(heatmap, use_container_width=True)

        grouped_bar = kontextus_funkcio_grouped_bar(ctx_fn, categories)
        if grouped_bar is not None:
            st.plotly_chart(grouped_bar, use_container_width=True)

    szerep_stats = summarize_kezdemenyezes_vs_valaszadas(events)
    if szerep_stats is not None:
        st.plotly_chart(
            kezdemenyezes_valaszadas_100_bar(szerep_stats),
            use_container_width=True,
        )
        if szerep_stats.kihagyott_darab > 0:
            st.caption(
                f"A szerep 5 (\u00f6sszesen {szerep_stats.kihagyott_darab} esem\u00e9ny: "
                "nem interakt\u00edv / nincs v\u00e1lasz) nem szerepel az ar\u00e1nyl\u00e1sban."
            )
    else:
        st.info(
            "Kezdem\u00e9nyez\u00e9s vs v\u00e1laszad\u00e1s: nincs "
            "1-es vagy 2/3/4/6-os szerepk\u00f3d\u00fa esem\u00e9ny."
        )

    st.subheader("\u00d6sszes\u00edt\u0151 t\u00e1bl\u00e1k")
    for dim, table in summaries.items():
        if table.empty:
            continue
        with st.expander(DIMENSION_TITLES.get(dim, dim)):
            st.dataframe(table, use_container_width=True, hide_index=True)

    _render_compare_upload_section()
    _render_comparison_results(events, summaries, categories)

    _render_pdf_download(survey, events, categories)


def main() -> None:
    st.set_page_config(page_title="M-COSMIC", layout="wide")
    st.title("M-COSMIC feldolgoz\u00e1s \u00e9s vizualiz\u00e1ci\u00f3")
    st.markdown(
        "Az **M-COSMIC** (Modified-Classroom Observation Schedule to Measure Intentional Communication) "
        "oszt\u00e1lytermi megfigyel\u00e9ssel r\u00f6gz\u00edti a gyermek sz\u00e1nd\u00e9kos kommunik\u00e1ci\u00f3j\u00e1t. "
        "T\u00f6lts fel egy kit\u00f6lt\u00f6tt CSV vagy Excel felm\u00e9r\u00e9si f\u00e1jlt az \u00f6sszes\u00edt\u00e9shez \u00e9s diagramokhoz."
    )

    _init_session_state()
    upload = _render_upload_section()

    if upload is None:
        st.info("Kezd\u00e9shez t\u00f6lts fel egy CSV vagy Excel f\u00e1jlt.")
        return

    name, data = upload
    try:
        survey = parse_bytes(data, filename=name)
    except Exception as exc:
        st.error(f"A f\u00e1jl feldolgoz\u00e1sa sikertelen: {exc}")
        if st.button("M\u00e1sik f\u00e1jl felt\u00f6lt\u00e9se"):
            _clear_upload()
            st.rerun()
        return

    _render_results(survey)


if __name__ == "__main__":
    main()
