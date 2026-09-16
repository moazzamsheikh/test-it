"""M4.2 — renders the same `ParcelReport` used by the JSON endpoint
(`app/services/report.py`) into a clean A4 PDF via Jinja2 + WeasyPrint (see
DECISIONS.md for the library choice). One template, one data source — the
PDF can never show numbers the JSON report doesn't, by construction.

Determinism: the brief asks for "the same parcel and the same corpus state
produce a byte-comparable PDF", but also requires a generation/freshness
timestamp on every page footer — those two requirements conflict under a
literal wall-clock "rendered at" timestamp (regenerating an hour later would
change the file even though nothing in the corpus did). Resolved by using
the real `data_freshness.newest_source_last_success_at` (M2.1's own source
tracking) as the footer's "Data as of" timestamp instead of `datetime.now()`
— this only changes when the underlying ingested data actually changes,
which is what "corpus state" means. The one exception to full determinism
is the embedded map-extract image: a real basemap tile fetched from a
government WMS at render time, not something this project controls (see
`app/services/report_map.py`).
"""

from __future__ import annotations

import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.schemas.report import ParcelReport

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _data_as_of(report: ParcelReport) -> str:
    ts = report.data_freshness.newest_source_last_success_at
    return ts.strftime("%Y-%m-%d %H:%M UTC") if ts is not None else "unknown"


def render_report_html(report: ParcelReport, map_png: bytes | None) -> str:
    template = _env.get_template("report.html.j2")
    map_image_base64 = base64.b64encode(map_png).decode("ascii") if map_png else None
    return template.render(
        report=report, map_image_base64=map_image_base64, data_as_of=_data_as_of(report)
    )


def render_report_pdf(report: ParcelReport, map_png: bytes | None) -> bytes:
    html = render_report_html(report, map_png)
    pdf_bytes: bytes = HTML(string=html).write_pdf()
    return pdf_bytes
