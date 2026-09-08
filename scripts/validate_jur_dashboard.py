#!/usr/bin/env python3
"""Validate the JUR dashboard before publishing, independently of its title."""
from __future__ import annotations

import json
import math
import sys
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA_START = "const DATA="
DATA_END = ";\nconst C="


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


class DashboardHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        element_id = dict(attrs).get("id")
        if element_id:
            self.elements[element_id] = tag
        if tag == "script":
            self.in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, value):
        if self.in_script:
            self.scripts[-1] += value


def latest_value(values, labels, name):
    require(isinstance(values, list) and len(values) == len(labels),
            f"{name}: antal værdier svarer ikke til antal perioder")
    value = values[-1]
    require(type(value) in (int, float) and math.isfinite(value),
            f"{name}: seneste værdi mangler eller er ikke et endeligt tal")
    return value


def validate(html, data):
    document = DashboardHTML()
    document.feed(html)
    require(document.elements.get("dak-analyse-jur") == "div",
            "index.html: dashboardets rod #dak-analyse-jur mangler")
    for element_id, tag in (("kpiGrid", "div"),
                            ("unemploymentPercentChart", "canvas"),
                            ("bankruptciesChart", "canvas")):
        require(document.elements.get(element_id) == tag,
                f"index.html: {tag}#{element_id} mangler")

    scripts = [script for script in document.scripts if DATA_START in script]
    require(len(scripts) == 1 and scripts[0].count(DATA_START) == 1,
            "index.html: forventede præcis én const DATA= i et script")
    payload = scripts[0].split(DATA_START, 1)[1]
    require(DATA_END in payload, "index.html: DATA-blokkens afslutning mangler")
    try:
        embedded = json.loads(payload.split(DATA_END, 1)[0])
    except json.JSONDecodeError as exc:
        raise ValidationError(f"index.html: ugyldig JSON i DATA-blokken: {exc}") from exc
    require(embedded == data,
            "index.html: indlejret DATA afviger fra data/dashboard-data.json")

    status = data["meta"]["updateStatus"]
    require(status.get("state") == "ok" and not status.get("failed"),
            f"Dataopdateringen er ikke fuldført: {status.get('state')}; "
            f"fejlede kilder: {status.get('failed')}")
    periods = {}
    for source, section_name in (("AUP03", "unemploymentPercent"),
                                 ("KONK3", "bankruptcies")):
        source_status = data["meta"]["sourceStatus"].get(source, {})
        period = source_status.get("latestPeriod")
        require(source_status.get("state") == "ok" and period,
                f"{source}: kildestatus er ikke ok eller latestPeriod mangler")
        section = data["sections"][section_name]
        labels = section["labels"]
        require(isinstance(labels, list) and labels,
                f"{source}: perioder mangler")
        require(labels[-1] == period,
                f"{source}: grafens seneste periode {labels[-1]} "
                f"matcher ikke kildens {period}")
        value = latest_value(section["total"], labels, f"{source} i alt")
        if source == "AUP03":
            require(isinstance(section["byAkasse"], dict) and section["byAkasse"],
                    "AUP03: a-kasseserier mangler")
            for name, values in section["byAkasse"].items():
                latest_value(values, labels, f"AUP03 / {name}")
        require(section["kpi"]["period"] == period,
                f"{source}: KPI-perioden matcher ikke kildens {period}")
        require(section["kpi"]["value"] == value,
                f"{source}: KPI-værdien matcher ikke grafens seneste værdi")
        periods[source] = period
    return periods


def main():
    try:
        for path in (BASE / "index.html", BASE / "data/dashboard-data.json"):
            require(path.is_file() and path.stat().st_size > 0,
                    f"{path.relative_to(BASE)}: filen mangler eller er tom")
        data = json.loads((BASE / "data/dashboard-data.json").read_text(encoding="utf-8"))
        periods = validate((BASE / "index.html").read_text(encoding="utf-8"), data)
    except (ValidationError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"FEJL: Dashboardvalidering: {exc}", file=sys.stderr)
        return 1
    print("OK: HTML-struktur, indlejrede data, kildestatus, perioder og KPI'er; "
          + ", ".join(f"{source}={period}" for source, period in periods.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
