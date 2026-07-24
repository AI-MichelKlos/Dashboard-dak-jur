#!/usr/bin/env python3
"""Find safe metadata for Jobindsats series used by the JUR dashboard."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


API_ROOT = "https://api.jobindsats.dk/v3"
KEYWORDS = (
    r"ledighed",
    r"langtidsledig",
    r"aktivering",
    r"vejledning",
    r"opkvalificering",
    r"virksomhedspraktik",
    r"løntilskud",
    r"varsl",
    r"arbejdsfordeling",
    r"rekruttering",
    r"dimittend",
    r"dagpengeret",
    r"sanktion",
)
RELEVANT_VALUE_WORDS = (
    "hele landet",
    "a-kasse",
    "akasse",
    "aktivering",
    "vejledning",
    "opkvalificering",
    "virksomhedspraktik",
    "løntilskud",
    "arbejdsfordeling",
    "dimittend",
    "sanktion",
    "rådighed",
    "varsling",
    "afskedig",
)


def api_get(path: str):
    token = os.environ.get("JOBINDSATS_API_TOKEN")
    if not token:
        raise RuntimeError("JOBINDSATS_API_TOKEN mangler")
    request = urllib.request.Request(
        f"{API_ROOT}/{path.lstrip('/')}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Danske-A-kasser-jur-dashboard/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Jobindsats returnerede HTTP {exc.code}: {detail[:500]}"
        ) from exc


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def first_text(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def table_id(item: dict) -> str:
    return first_text(item, ("table_id", "tableId", "id"))


def table_title(item: dict) -> str:
    return first_text(item, ("table_name", "tableName", "name", "title", "text"))


def compact_values(values) -> list[dict]:
    found = []
    for item in walk(values):
        if not isinstance(item, dict):
            continue
        identifier = first_text(item, ("id", "value", "code"))
        name = first_text(item, ("name", "text", "title", "label"))
        if not identifier or not name:
            continue
        lowered = name.lower()
        if identifier == "/" or any(word in lowered for word in RELEVANT_VALUE_WORDS):
            row = {"id": identifier, "name": name}
            if row not in found:
                found.append(row)
    return found[:40]


def summarize_metadata(metadata) -> dict:
    if not isinstance(metadata, dict):
        return {"response_type": type(metadata).__name__}

    measures = []
    for item in walk(metadata.get("mgroups", [])):
        if not isinstance(item, dict):
            continue
        identifier = first_text(item, ("id", "mgroup_id", "code"))
        name = first_text(item, ("name", "text", "title", "label"))
        if identifier and name and {"id": identifier, "name": name} not in measures:
            measures.append({"id": identifier, "name": name})

    dimensions = []
    for item in metadata.get("dimensions", []):
        if not isinstance(item, dict):
            continue
        identifier = first_text(item, ("id", "dimension_id", "code"))
        name = first_text(item, ("name", "text", "title", "label"))
        values = compact_values(item)
        if identifier or name:
            dimensions.append(
                {"id": identifier, "name": name, "relevant_values": values}
            )

    periods = []
    for item in walk(metadata.get("periods", [])):
        if not isinstance(item, dict):
            continue
        identifier = first_text(item, ("id", "period_id", "code"))
        name = first_text(item, ("name", "text", "title", "label"))
        if identifier and name:
            periods.append({"id": identifier, "name": name})

    return {
        "measures": measures[:30],
        "dimensions": dimensions[:30],
        "period_examples": periods[-4:],
    }


def main():
    catalog = api_get("tables?format=json")
    candidates = {}
    for item in walk(catalog):
        identifier = table_id(item)
        title = table_title(item)
        if not identifier or not title or identifier in candidates:
            continue
        haystack = json.dumps(item, ensure_ascii=False).lower()
        if any(re.search(pattern, haystack, re.IGNORECASE) for pattern in KEYWORDS):
            candidates[identifier] = title

    print(f"API-forbindelsen virker. Fandt {len(candidates)} kandidattabeller.")
    for identifier in sorted(candidates):
        print()
        print(f"TABLE {identifier}: {candidates[identifier]}")
        metadata = api_get(f"table/{identifier}?format=json")
        print(json.dumps(summarize_metadata(metadata), ensure_ascii=False))


if __name__ == "__main__":
    main()
