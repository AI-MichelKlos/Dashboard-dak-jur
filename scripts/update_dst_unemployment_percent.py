#!/usr/bin/env python3
"""Refresh JUR unemployment percentages from Statistics Denmark table AUP03."""
from __future__ import annotations

import csv
import io
import urllib.parse
import urllib.request

TABLE = "AUP03"
API_URL = f"https://api.statbank.dk/v1/data/{TABLE}/CSV"


def _fund_name(dst_name: str) -> str | None:
    """Map current AUP03 fund labels to the dashboard's stable display names."""
    name = (dst_name or "").strip()
    low = name.casefold()
    if name == "I alt":
        return "__total__"
    rules = (
        ("akademik", "Akademikernes A-kasse"),
        ("din faglige", "Din Faglige A-kasse"),
        ("børne- og ungdomspædagog", "Børne- og Ungdomspædagogernes Landsdækkende A-kasse"),
        ("sundhedsfag", "Din Sundhedsfaglige A-kasse"),
        ("det faglige hus", "Det Faglige Hus - A-kasse"),
        ("fag og arbejde", "FOAs A-kasse"),
        ("faglig fælles", "Faglig Fælles A-kasse"),
        ("a-kassen frie", "A-kassen Frie"),
        ("journalistik", "A-kassen for Journalistik, Kommunikation & Sprog"),
        ("kristelig", "Kristelig A-kasse"),
        ("ledere", "Lederne A-kasse"),
        ("lærere", "Lærernes a-kasse"),
        ("magistre", "Magistrenes A-kasse"),
        ("metalarbejd", "Metal A-kasse"),
        ("min a-kasse", "Min A-kasse"),
        ("min akasse", "Min A-kasse"),
        ("socialpædagog", "Socialpædagogernes A-kasse"),
        ("tekniker", "Teknikernes A-kasse"),
        ("ase", "ASE"),
        ("a&til", "A-kassen A&Til"),
        ("a og til", "A-kassen A&Til"),
        ("funktionærer og tjenestemænd", "A-kassen A&Til"),
        ("hk", "HK A-kasse"),
    )
    for needle, target in rules:
        if needle in low:
            return target
    return None


def _number(value: str):
    text = (value or "").strip().replace(" ", "")
    if not text or text in {"-", ".."}:
        return None
    return round(float(text.replace(".", "").replace(",", ".")), 4)


def _fetch_rows():
    params = [
        ("OMRÅDE", "000"),
        ("ALDER", "TOT"),
        ("KØN", "TOT"),
        ("AKASSE", "*"),
        ("Tid", "*"),
    ]
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Accept": "text/csv", "User-Agent": "Danske-A-kasser-jur-dashboard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def refresh(data, kpi_func):
    """Merge all available AUP03 observations into sections.unemploymentPercent."""
    sec = data["sections"]["unemploymentPercent"]
    old_labels = list(sec["labels"])
    cutoff = old_labels[0] if old_labels else ""
    total_updates: dict[str, float | None] = {}
    fund_updates: dict[str, dict[str, float | None]] = {}

    for row in _fetch_rows():
        period = str(row.get("TID") or row.get("Tid") or "")
        if not period or (cutoff and period < cutoff):
            continue
        mapped = _fund_name(str(row.get("AKASSE") or ""))
        if not mapped:
            continue
        value = _number(str(row.get("INDHOLD") or ""))
        if mapped == "__total__":
            total_updates[period] = value
        elif mapped in sec["byAkasse"]:
            fund_updates.setdefault(mapped, {})[period] = value

    if not total_updates:
        raise RuntimeError("AUP03 returnerede ingen gyldige totalobservationer")

    latest = max(total_updates)
    if latest <= old_labels[-1]:
        # Still merge revisions to existing periods even when no new period exists.
        pass

    labels = sorted(set(old_labels) | set(total_updates) | {p for values in fund_updates.values() for p in values})
    old_total = dict(zip(old_labels, sec["total"]))
    sec["labels"] = labels
    sec["total"] = [total_updates.get(period, old_total.get(period)) for period in labels]

    updated_by_fund = {}
    for fund, old_values in sec["byAkasse"].items():
        merged = dict(zip(old_labels, old_values))
        merged.update(fund_updates.get(fund, {}))
        updated_by_fund[fund] = [merged.get(period) for period in labels]
    sec["byAkasse"] = updated_by_fund
    kpi_func(sec, sec["total"])

    missing_latest = [
        fund for fund in sec["byAkasse"]
        if fund not in fund_updates or latest not in fund_updates[fund]
    ]
    # A fund can legitimately be absent after mergers, but widespread misses indicate mapping/API drift.
    if len(missing_latest) > 3:
        raise RuntimeError(
            f"AUP03 {latest} mangler mapping for {len(missing_latest)} a-kasser: "
            + ", ".join(missing_latest[:8])
        )

    return latest
