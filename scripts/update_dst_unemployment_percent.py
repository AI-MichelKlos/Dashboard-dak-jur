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
        ("journalistik", "A-kassen for Journalistik, Kommunikation & Sprog"),
        ("a-kassen frie", "A-kassen Frie"),
        ("akademik", "Akademikernes A-kasse"),
        ("din faglige", "Din Faglige A-kasse"),
        ("børne- og ungdomspædagog", "Børne- og Ungdomspædagogernes Landsdækkende A-kasse"),
        ("sundhedsfag", "Din Sundhedsfaglige A-kasse"),
        ("det faglige hus", "Det Faglige Hus - A-kasse"),
        ("fag og arbejde", "FOAs A-kasse"),
        ("faglig fælles", "Faglig Fælles A-kasse"),
        ("ca a-kasse", "CA A-kasse & Karriereudvikling"),
        ("ca a-kasse &", "CA A-kasse & Karriereudvikling"),
        ("kristelig", "Kristelig A-kasse"),
        ("lederne", "Lederne A-kasse"),
        ("lærernes", "Lærernes a-kasse"),
        ("magistr", "Magistrenes A-kasse"),
        ("metal", "Metal A-kasse"),
        ("min a-kasse", "Min A-kasse"),
        ("min akasse", "Min A-kasse"),
        ("socialpædagog", "Socialpædagogernes A-kasse"),
        ("tekniker", "Teknikernes A-kasse"),
        ("ase", "ASE"),
        ("a&til", "A-kassen A&Til"),
        ("a og til", "A-kassen A&Til"),
        ("funktionærer og tjenestemænd", "A-kassen A&Til"),
        ("ftf-a", "A-kassen A&Til"),
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
    """Refresh only AUP03's latest period and leave existing history untouched."""
    sec = data["sections"]["unemploymentPercent"]
    old_labels = list(sec["labels"])
    rows = _fetch_rows()

    totals = {}
    for row in rows:
        if str(row.get("AKASSE") or "").strip() != "I alt":
            continue
        period = str(row.get("TID") or row.get("Tid") or "")
        if period:
            totals[period] = _number(str(row.get("INDHOLD") or ""))
    if not totals:
        raise RuntimeError("AUP03 returnerede ingen gyldige totalobservationer")

    latest = max(totals)
    latest_total = totals[latest]
    if latest_total is None:
        raise RuntimeError(f"AUP03 {latest} mangler totalværdi")

    candidates: dict[str, list[float]] = {}
    for row in rows:
        period = str(row.get("TID") or row.get("Tid") or "")
        if period != latest:
            continue
        mapped = _fund_name(str(row.get("AKASSE") or ""))
        if not mapped or mapped == "__total__" or mapped not in sec["byAkasse"]:
            continue
        value = _number(str(row.get("INDHOLD") or ""))
        if value is not None:
            candidates.setdefault(mapped, []).append(value)

    latest_by_fund = {fund: max(values) for fund, values in candidates.items() if values}
    missing = [fund for fund in sec["byAkasse"] if fund not in latest_by_fund]
    if missing:
        raise RuntimeError(
            f"AUP03 {latest} mangler mapping for {len(missing)} a-kasser: "
            + ", ".join(missing)
        )

    if latest in old_labels:
        idx = old_labels.index(latest)
        sec["total"][idx] = latest_total
        for fund, values in sec["byAkasse"].items():
            values[idx] = latest_by_fund[fund]
    else:
        if old_labels and latest < old_labels[-1]:
            raise RuntimeError(
                f"AUP03 seneste periode {latest} er ældre end dashboardets {old_labels[-1]}"
            )
        sec["labels"].append(latest)
        sec["total"].append(latest_total)
        for fund, values in sec["byAkasse"].items():
            values.append(latest_by_fund[fund])

    kpi_func(sec, sec["total"])
    return latest
