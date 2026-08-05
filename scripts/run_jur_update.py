#!/usr/bin/env python3
"""Robust entrypoint for the automated JUR dashboard update."""
from __future__ import annotations

import json
import math
import re
import time
import urllib.error
from datetime import datetime
from html import escape as html_escape
from zoneinfo import ZoneInfo

import update_jur_dashboard as updater


NULL_TOKENS = {"", "-", ".", "..", "null", "none", "nan"}
MONTH_LIMIT = 24
QUARTER_LIMIT = 12
MAX_ATTEMPTS = 2


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


def compact_period_request(path):
    path = re.sub(r"period\.M=latest:\d+", f"period.M=latest:{MONTH_LIMIT}", path, count=1)
    return re.sub(r"period\.Q=latest:\d+", f"period.Q=latest:{QUARTER_LIMIT}", path, count=1)


def adjust_available_periods(path, message):
    match = re.search(
        r"Requested latest:(\d+) for type ([MQ]), but only (\d+) periods are available",
        message,
    )
    if not match:
        return None
    period_type = match.group(2)
    available = match.group(3)
    adjusted_path = re.sub(
        rf"period\.{period_type}=latest:\d+",
        f"period.{period_type}=latest:{available}",
        path,
        count=1,
    )
    if adjusted_path == path:
        return None
    print(
        f"Jobindsats har kun {available} perioder for type {period_type}; "
        "kaldet tilpasses automatisk.",
        flush=True,
    )
    return adjusted_path


def retryable_runtime_error(exc):
    message = str(exc)
    return any(f"HTTP {code}" in message for code in (429, 500, 502, 503, 504))


def resilient_api_get(path):
    """Use smaller requests and retry transient Jobindsats failures per API call."""
    request_path = compact_period_request(path)
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _original_api_get(request_path)
        except RuntimeError as exc:
            adjusted_path = adjust_available_periods(request_path, str(exc))
            if adjusted_path:
                request_path = adjusted_path
                try:
                    return _original_api_get(request_path)
                except Exception as adjusted_exc:
                    last_error = adjusted_exc
            elif retryable_runtime_error(exc):
                last_error = exc
            else:
                raise
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            last_error = exc

        if attempt < MAX_ATTEMPTS:
            pause = attempt * 15
            print(
                f"Jobindsats-kald fejlede, forsøg {attempt} af {MAX_ATTEMPTS}. "
                f"Prøver igen om {pause} sekunder: {request_path}",
                flush=True,
            )
            time.sleep(pause)

    raise RuntimeError(
        f"Jobindsats-kald fejlede efter {MAX_ATTEMPTS} forsøg: {request_path}: {last_error}"
    ) from last_error


def sync_visible_date(data):
    """Keep the visible HTML date and update status aligned with metadata."""
    version_date = str(data.get("meta", {}).get("versionDate", "")).strip()
    if not version_date:
        raise RuntimeError("Dashboardets versionDate mangler")

    status = data.get("meta", {}).get("updateStatus", {})
    state = status.get("state", "ok")
    visible = html_escape(version_date)
    if state == "partial":
        failed = ", ".join(html_escape(str(item)) for item in status.get("failed", []))
        visible += (
            '<br><span style="font-size:12px;color:#8a5a00">'
            f"Delvist opdateret. Viser seneste gyldige data for: {failed}."
            "</span>"
        )
    elif state == "stale":
        visible += (
            '<br><span style="font-size:12px;color:#a12622">'
            "Seneste opdateringsforsøg fejlede. Dashboardet viser seneste gyldige data."
            "</span>"
        )

    dashboard_html = updater.HTML_PATH.read_text(encoding="utf-8")
    pattern = (
        r'(<section class="date-box" aria-label="Dato for versionen">)'
        r'.*?'
        r'(</section>)'
    )
    updated_html, replacements = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{visible}{match.group(2)}",
        dashboard_html,
        count=1,
        flags=re.DOTALL,
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

    successes = []
    failures = []
    for label, refresh in refreshers:
        print(f"Starter: {label}", flush=True)
        try:
            refresh(data)
        except Exception as exc:
            failures.append(label)
            print(f"ADVARSEL: {label} blev ikke opdateret: {exc}", flush=True)
            continue
        successes.append(label)
        print(f"Færdig: {label}", flush=True)

    after_refresh = json.dumps(data, ensure_ascii=False, sort_keys=True)
    numbers_changed = before != after_refresh
    now = datetime.now(ZoneInfo("Europe/Copenhagen"))
    state = "ok" if not failures else ("partial" if successes else "stale")
    update_status = {
        "state": state,
        "successful": successes,
        "failed": failures,
        "periodsFetchedPerRun": {"months": MONTH_LIMIT, "quarters": QUARTER_LIMIT},
    }
    if state != "ok":
        update_status["checkedAt"] = now.isoformat(timespec="seconds")
    data.setdefault("meta", {})["updateStatus"] = update_status

    if successes and (numbers_changed or not had_data_file):
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

    if state == "ok":
        if numbers_changed or not had_data_file:
            print(f"JUR-dashboardet er opdateret: {data['meta']['versionDate']}.")
        else:
            print("Ingen nye eller ændrede Jobindsats-tal; HTML-datoen er synkroniseret.")
        return
    if state == "partial":
        print(
            "JUR-dashboardet blev delvist opdateret. Seneste gyldige data er bevaret "
            f"for: {', '.join(failures)}.",
            flush=True,
        )
        return

    raise RuntimeError(
        "Alle JUR-datasæt fejlede. Seneste gyldige data er bevaret og markeret i dashboardet."
    )


if __name__ == "__main__":
    main()
