#!/usr/bin/env python3
"""Fetch small public Jobindsats samples used to validate the JUR updater."""

from __future__ import annotations

import json
from pathlib import Path

from discover_jur_sources import api_get


OUTPUT = Path("data/jur-api-probe.json")
QUERIES = {
    "unemployment_total": (
        "data/y25i01?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._ygrpi09=/"
        "&hierarchy._akassebl=/&format=json"
    ),
    "unemployment_akasser": (
        "data/y25i01?mgroup.*=*&period.M=latest:2"
        "&hierarchy._nykom=/&hierarchy._ygrpi09=/"
        "&hierarchy._akassebl=*&format=json"
    ),
    "longterm_total": (
        "data/y25i09?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._ygrpi09=/"
        "&hierarchy._akassebl=/&format=json"
    ),
    "longterm_akasser": (
        "data/y25i09?mgroup.*=*&period.M=latest:2"
        "&hierarchy._nykom=/&hierarchy._ygrpi09=/"
        "&hierarchy._akassebl=*&format=json"
    ),
    "activation": (
        "data/y01c01?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._akassedp=/"
        "&hierarchy._tilb_2ptv=*&format=json"
    ),
    "notices": (
        "data/y25i05?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&format=json"
    ),
    "work_sharing": (
        "data/y25i06?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._var13uger=*&format=json"
    ),
    "new_work_sharing": (
        "data/y25i06b?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._var13uger=*&format=json"
    ),
    "recruitment": (
        "data/y25i14?mgroup.*=*&period.M=latest:8"
        "&hierarchy._hele_landet=/&hierarchy._escostar_rs=/&format=json"
    ),
    "graduates_total": (
        "data/y01dia02?mgroup.*=*&period.M=latest:14"
        "&hierarchy._nykom=/&hierarchy._akassedp=/&format=json"
    ),
    "graduates_akasser": (
        "data/y01dia02?mgroup.*=*&period.M=latest:2"
        "&hierarchy._nykom=/&hierarchy._akassedp=*&format=json"
    ),
    "expired_graduates": (
        "data/y01ud01di?mgroup.*=*&period.M=latest:14"
        "&hierarchy._hele_landet=/&hierarchy._akassedp=/"
        "&hierarchy._dimittend=*&hierarchy._forlang=/&format=json"
    ),
    "sanctions_total": (
        "data/y01h01?mgroup.*=*&period.Q=latest:6"
        "&hierarchy._nykom=/&hierarchy._akassedp=/&format=json"
    ),
    "sanctions_akasser": (
        "data/y01h01?mgroup.*=*&period.Q=latest:2"
        "&hierarchy._nykom=/&hierarchy._akassedp=*&format=json"
    ),
}


def main():
    results = {}
    failures = {}
    for name, query in QUERIES.items():
        try:
            results[name] = api_get(query)
            print(f"OK {name}")
        except Exception as exc:
            failures[name] = str(exc)
            print(f"FEJL {name}: {exc}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"results": results, "failures": failures}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    if failures:
        print(f"{len(failures)} prøveforespørgsler fejlede, se resultatfilen.")


if __name__ == "__main__":
    main()
