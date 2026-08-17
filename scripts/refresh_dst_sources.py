#!/usr/bin/env python3
"""Refresh Statistics Denmark sources used by the JUR dashboard and persist status."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import update_jur_dashboard as updater
import update_dst_bankruptcies as dst_bankruptcies
import update_dst_unemployment_percent as dst_percent

AUP03_LABEL = "ledighed i pct. (DST AUP03)"
KONK3_LABEL = "konkurser (DST KONK3)"


def main():
    data, _ = updater.load_data()
    meta = data.setdefault("meta", {})
    status = meta.setdefault("updateStatus", {})
    successes = list(status.get("successful", []))
    failures = list(status.get("failed", []))
    now = datetime.now(ZoneInfo("Europe/Copenhagen"))

    source_status = meta.setdefault("sourceStatus", {})

    try:
        latest_aup03 = dst_percent.refresh(data, updater.kpi)
    except Exception as exc:
        if AUP03_LABEL not in failures:
            failures.append(AUP03_LABEL)
        successes = [item for item in successes if item != AUP03_LABEL]
        source_status["AUP03"] = {
            "state": "failed",
            "checkedAt": now.isoformat(timespec="seconds"),
            "error": str(exc),
        }
    else:
        failures = [item for item in failures if item != AUP03_LABEL]
        if AUP03_LABEL not in successes:
            successes.append(AUP03_LABEL)
        source_status["AUP03"] = {
            "state": "ok",
            "latestPeriod": latest_aup03,
            "checkedAt": now.isoformat(timespec="seconds"),
            "source": "Danmarks Statistik",
            "dataset": "AUP03",
        }

    try:
        latest_konk3, source_updated = dst_bankruptcies.refresh(data, updater.kpi)
    except Exception as exc:
        if KONK3_LABEL not in failures:
            failures.append(KONK3_LABEL)
        successes = [item for item in successes if item != KONK3_LABEL]
        source_status["KONK3"] = {
            "state": "failed",
            "checkedAt": now.isoformat(timespec="seconds"),
            "error": str(exc),
        }
    else:
        failures = [item for item in failures if item != KONK3_LABEL]
        if KONK3_LABEL not in successes:
            successes.append(KONK3_LABEL)
        source_status["KONK3"] = {
            "state": "ok",
            "latestPeriod": latest_konk3,
            "sourceUpdated": source_updated,
            "checkedAt": now.isoformat(timespec="seconds"),
            "source": "Danmarks Statistik",
            "dataset": "KONK3",
        }

    status.update({
        "state": "ok" if not failures else ("partial" if successes else "stale"),
        "successful": successes,
        "failed": failures,
        "checkedAt": now.isoformat(timespec="seconds"),
    })

    updater.DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    updater.render(data)

    if failures:
        raise RuntimeError("DST-opdatering fejlede for: " + ", ".join(failures))

    print(f"DST AUP03 opdateret til {latest_aup03}.")
    print(f"DST KONK3 opdateret til {latest_konk3}.")


if __name__ == "__main__":
    main()
