#!/usr/bin/env python3
"""Refresh Statistics Denmark sources used by the JUR dashboard and persist status."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import update_jur_dashboard as updater
import update_dst_unemployment_percent as dst_percent

LABEL = "ledighed i pct. (DST AUP03)"


def main():
    data, _ = updater.load_data()
    meta = data.setdefault("meta", {})
    status = meta.setdefault("updateStatus", {})
    successes = list(status.get("successful", []))
    failures = list(status.get("failed", []))
    now = datetime.now(ZoneInfo("Europe/Copenhagen"))

    try:
        latest = dst_percent.refresh(data, updater.kpi)
    except Exception as exc:
        if LABEL not in failures:
            failures.append(LABEL)
        successes = [item for item in successes if item != LABEL]
        status.update({
            "state": "partial" if successes else "stale",
            "successful": successes,
            "failed": failures,
            "checkedAt": now.isoformat(timespec="seconds"),
        })
        meta.setdefault("sourceStatus", {})["AUP03"] = {
            "state": "failed",
            "checkedAt": now.isoformat(timespec="seconds"),
            "error": str(exc),
        }
        updater.DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updater.render(data)
        raise

    failures = [item for item in failures if item != LABEL]
    if LABEL not in successes:
        successes.append(LABEL)
    status.update({
        "state": "ok" if not failures else "partial",
        "successful": successes,
        "failed": failures,
        "checkedAt": now.isoformat(timespec="seconds"),
    })
    meta.setdefault("sourceStatus", {})["AUP03"] = {
        "state": "ok",
        "latestPeriod": latest,
        "checkedAt": now.isoformat(timespec="seconds"),
        "source": "Danmarks Statistik",
        "dataset": "AUP03",
    }
    updater.DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    updater.render(data)
    print(f"DST AUP03 opdateret til {latest}.")


if __name__ == "__main__":
    main()
