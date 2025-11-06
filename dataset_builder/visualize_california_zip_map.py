"""Render a California ZIP choropleth for unified_vehicle_listings."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import folium
import pandas as pd
import requests

DEFAULT_DB = Path("data/unified_vehicles.db")
DEFAULT_OUTPUT = Path("data/california_zip_map.html")
DEFAULT_GEOJSON = Path("dataset_builder/ca_california_zip_codes.geojson")
GEOJSON_URL = (
    "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/ca_california_zip_codes_geo.min.json"
)


def ensure_geojson(path: Path, url: str = GEOJSON_URL) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Unable to download California ZIP GeoJSON from {url}. "
            "Pass --geojson with a local file instead."
        ) from exc
    path.write_text(response.text, encoding="utf-8")
    return path


def load_zip_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    cursor = conn.execute(
        """
        SELECT dealer_zip
        FROM unified_vehicle_listings
        WHERE dealer_state = 'CA' AND dealer_zip IS NOT NULL AND dealer_zip != ''
        """
    )
    counts: Dict[str, int] = {}
    for (zip_code,) in cursor.fetchall():
        if zip_code is None:
            continue
        digits = str(zip_code).strip()
        if not digits:
            continue
        digits = digits[:5]
        if not digits.isdigit():
            continue
        counts[digits] = counts.get(digits, 0) + 1
    return counts


def _infer_property(
    properties: Dict[str, object],
    candidates: Iterable[str],
    fallback_contains: Iterable[str],
) -> Optional[str]:
    for key in candidates:
        if key in properties:
            return key
    lowered = {key.lower(): key for key in properties}
    for needle in fallback_contains:
        for lower_key, original_key in lowered.items():
            if needle in lower_key:
                return original_key
    return None


def _detect_geojson_keys(feature: Dict[str, object]) -> Tuple[str, Optional[str]]:
    properties = feature.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("GeoJSON features must include a properties dictionary.")

    zip_key = _infer_property(
        properties,
        candidates=(
            "zip",
            "ZIP",
            "zipcode",
            "Zip",
            "ZCTA5CE10",
            "ZCTA5CE",
            "ZCTA5",
            "POSTCODE",
            "postalCode",
        ),
        fallback_contains=("zip", "postal"),
    )
    if zip_key is None:
        raise ValueError("Unable to identify a ZIP code property in the GeoJSON data.")

    city_key = _infer_property(
        properties,
        candidates=("city", "City", "CITY", "PO_NAME", "place"),
        fallback_contains=("city", "place"),
    )
    return zip_key, city_key


def build_map(zip_counts: Dict[str, int], geojson_path: Path) -> folium.Map:
    if not zip_counts:
        raise ValueError("No California ZIP counts available to visualize.")

    data = pd.DataFrame([(zip_code, count) for zip_code, count in zip_counts.items()], columns=["zip", "count"])
    data["zip"] = data["zip"].astype(str)

    with geojson_path.open("r", encoding="utf-8") as handle:
        geojson = json.load(handle)

    features = geojson.get("features")
    if not features:
        raise ValueError("GeoJSON file does not contain any features to visualize.")

    zip_property, city_property = _detect_geojson_keys(features[0])

    choropleth = folium.Map(location=[36.7783, -119.4179], zoom_start=6, tiles="cartodbpositron")
    folium.Choropleth(
        geo_data=geojson,
        name="zip density",
        data=data,
        columns=["zip", "count"],
        key_on=f"feature.properties.{zip_property}",
        fill_color="YlOrRd",
        fill_opacity=0.8,
        line_opacity=0.2,
        nan_fill_color="white",
        legend_name="Listings per ZIP",
    ).add_to(choropleth)

    tooltip_fields = [zip_property]
    tooltip_aliases = ["ZIP"]
    if city_property:
        tooltip_fields.append(city_property)
        tooltip_aliases.append("City")

    folium.GeoJson(
        geojson,
        name="zip boundaries",
        tooltip=folium.features.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases,
            localize=True,
        ),
    ).add_to(choropleth)

    folium.LayerControl().add_to(choropleth)
    return choropleth


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize California inventory by ZIP code")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Unified database path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="HTML map output path")
    parser.add_argument(
        "--geojson",
        type=Path,
        default=DEFAULT_GEOJSON,
        help="Path to a California ZIP GeoJSON file (downloaded automatically if missing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise FileNotFoundError(f"Database not found: {args.db}")

    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        counts = load_zip_counts(conn)

    geojson_path = ensure_geojson(args.geojson)
    map_object = build_map(counts, geojson_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    map_object.save(str(args.output))
    print(f"Map saved to {args.output}")


if __name__ == "__main__":
    main()
