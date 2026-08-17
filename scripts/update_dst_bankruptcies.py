#!/usr/bin/env python3
"""Refresh JUR bankruptcy figures directly from Statistics Denmark KONK3."""
from __future__ import annotations

import json
import math
import urllib.request

API_URL = "https://api.statbank.dk/v1/data"
TABLE = "KONK3"
SERIES_CODE = "A"  # Erklærede konkurser i virksomheder med beskæftigelse, ikke sæsonkorrigeret


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace("\xa0", "").replace(" ", "")
        if text.lower() in {"", "-", ".", "..", "null", "none", "nan"}:
            return None
        value = float(text.replace(".", "").replace(",", ".") if "," in text else text)
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else round(number, 4)


def _positions(category):
    index = category.get("index")
    if isinstance(index, dict):
        return {str(code): int(pos) for code, pos in index.items()}
    if isinstance(index, list):
        return {str(code): pos for pos, code in enumerate(index)}
    labels = category.get("label")
    if isinstance(labels, dict):
        return {str(code): pos for pos, code in enumerate(labels)}
    raise RuntimeError("KONK3-svaret mangler kategoriindeks")


def _fetch():
    body = {
        "table": TABLE,
        "format": "JSONSTAT",
        "lang": "da",
        "variables": [
            {"code": "BNØGLE", "values": [SERIES_CODE]},
            {"code": "Tid", "values": ["*"]},
        ],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Danske-A-kasser-jur-dashboard/1.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))

    dataset = payload.get("dataset", payload)
    dimensions = dataset.get("dimension")
    if not isinstance(dimensions, dict):
        raise RuntimeError("KONK3-svaret mangler dimensioner")
    ids = dataset.get("id") or dimensions.get("id")
    sizes = dataset.get("size") or dimensions.get("size")
    values = dataset.get("value")
    if not isinstance(ids, list) or not isinstance(sizes, list):
        raise RuntimeError("KONK3-svaret mangler id/size")

    time_dim = next((item for item in ids if str(item).lower() == "tid"), None)
    series_dim = next((item for item in ids if str(item).lower() == "bnøgle"), None)
    if time_dim is None or series_dim is None:
        raise RuntimeError(f"KONK3-svaret mangler Tid eller BNØGLE: {ids}")

    time_positions = _positions(dimensions[time_dim]["category"])
    series_positions = _positions(dimensions[series_dim]["category"])
    if SERIES_CODE not in series_positions:
        raise RuntimeError(f"KONK3 returnerede ikke BNØGLE {SERIES_CODE}")

    labels = [code for code, _ in sorted(time_positions.items(), key=lambda item: item[1])]

    def flat_index(coords):
        idx = 0
        for coord, size in zip(coords, sizes):
            idx = idx * int(size) + coord
        return idx

    series = []
    for period in labels:
        coords = []
        for item in ids:
            if item == series_dim:
                coords.append(series_positions[SERIES_CODE])
            elif item == time_dim:
                coords.append(time_positions[period])
            else:
                coords.append(0)
        idx = flat_index(coords)
        if isinstance(values, list):
            raw = values[idx] if idx < len(values) else None
        elif isinstance(values, dict):
            raw = values.get(str(idx), values.get(idx))
        else:
            raise RuntimeError("KONK3-svaret mangler værdier")
        series.append(_number(raw))

    if not labels or not any(value is not None for value in series):
        raise RuntimeError("KONK3 returnerede ingen anvendelige konkurstal")
    return labels, series, dataset


def refresh(data, kpi_func):
    labels, values, dataset = _fetch()
    section = data["sections"]["bankruptcies"]
    section["labels"] = labels
    section["total"] = values
    kpi_func(section, values)
    return labels[-1], dataset.get("updated")
