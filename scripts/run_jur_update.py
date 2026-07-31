#!/usr/bin/env python3
"""Robust entrypoint for the automated JUR dashboard update."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import update_jur_dashboard as updater


NULL_TOKENS = {"", "-", ".", "..", "null", "none", "nan"}


def robust_num(value):
    """Parse Jobindsats values, including suppressed and blank cells."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("\xa0", "").replace(" ", "")
        if text.lower() in NULL_TOKENS:
            return None
        normalized = text.replace(".", "").replace(",", ".") if "," in text else text
        try:
            number = float(normalized)
        except ValueError as exc:
            raise ValueError(f"Uventet talformat fra Jobindsats: {value!r}") from exc
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else round(number, 4)


_original_api_get = updater.api_get


def resilient_api_get(path):
    """Retry when Jobindsats reports fewer available periods than requested."""
    try:
        return _original_api_get(path)
    except RuntimeError as exc:
        message = str(exc)
        match = re.search(
            r"Requested latest:(\d+) for type ([MQ]), but only (\d+) periods are available",
            message,
        )
        if not match:
            raise
        period_type = match.group(2)
        available = match.group(3)
        adjusted_path = re.sub(
            rf"period\.{period_type}=latest:\d+",
            f"period.{period_type}=latest:{available}",
            path,
            count=1,
        )
        if adjusted_path == path:
            raise
        print(
            f"Jobindsats har kun {available} perioder for type {period_type}; "
            "kaldet tilpasses automatisk.",
            flush=True,
        )
        return _original_api_get(adjusted_path)


def sync_visible_date(data):
    """Keep the visible HTML date aligned with meta.versionDate."""
    version_date = str(data.get("meta", {}).get("versionDate", "")).strip()
    if not version_date:
        raise RuntimeError("Dashboardets versionDate mangler")

    html = updater.HTML_PATH.read_text(encoding="utf-8")
    pattern = (
        r'(<section class="date-box" aria-label="Dato for versionen">)'
        r'.*?'
        r'(</section>)'
    )
    updated_html, replacements = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{version_date}{match.group(2)}",
        html,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("Kunne ikke finde den synlige datoboks i index.html")
    updater.HTML_PATH.write_text(updated_html, encoding="utf-8")


# Functions in update_jur_dashboard resolve these names dynamically.
updater.num = robust_num
updater.api_get = resilient_api_get


def main():
    data, had_data_file = updater.load_data()
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)

    refreshers = (
        ("ledighed fordelt på a-kasse", updater.refresh_unemployment),
        ("langtidsledighed", updater.refresh_longterm),
        ("aktiveringstilbud", updater.refresh_activation),
        ("varslede afskedigelser", updater.refresh_notices),
        ("arbejdsfordeling", updater.refresh_worksharing),
        ("dimittendledighed", updater.refresh_graduates),
        ("opbrugt dagpengeret", updater.refresh_expired),
        ("sanktioner", updater.refresh_sanctions),
    )

    for label, refresh in refreshers:
        print(f"Starter: {label}", flush=True)
        try:
            refresh(data)
        except Exception as exc:
            raise RuntimeError(f"JUR-opdateringen stoppede ved '{label}': {exc}") from exc
        print(f"Færdig: {label}", flush=True)

    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before == after and had_data_file:
        updater.render(data)
        sync_visible_date(data)
        print("Ingen nye eller ændrede Jobindsats-tal; HTML-datoen er synkroniseret.")
        return

    now = datetime.now(ZoneInfo("Europe/Copenhagen"))
    months = (
        "januar", "februar", "marts", "april", "maj", "juni",
        "juli", "august", "september", "oktober", "november", "december",
    )
    data["meta"]["versionDate"] = f"{now.day}. {months[now.month - 1]} {now.year}"
    data["meta"]["sourceFile"] = "Officielle API-kilder med tidligere Excel-data som fallback"

    updater.DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    updater.DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    updater.render(data)
    sync_visible_date(data)
    print(f"JUR-dashboardet er opdateret: {data['meta']['versionDate']}.")


if __name__ == "__main__":
    main()
