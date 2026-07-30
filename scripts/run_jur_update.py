#!/usr/bin/env python3
"""Robust entrypoint for the automated JUR dashboard update."""
from __future__ import annotations

import json
import math
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


# All functions in update_jur_dashboard resolve num dynamically from the module.
updater.num = robust_num


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
        print("Ingen nye eller ændrede Jobindsats-tal.")
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
    print(f"JUR-dashboardet er opdateret: {data['meta']['versionDate']}.")


if __name__ == "__main__":
    main()
