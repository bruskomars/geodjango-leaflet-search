"""
search/api_docs.py

OpenAPI documentation for the cross-model search endpoint, kept out of views.py
so the view stays readable. Use it as a decorator: @search_schema
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema


def _param(name, description, example):
    return OpenApiParameter(
        name=name,
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description=description,
        examples=[OpenApiExample(f"{name} example", value=example)],
    )


DESCRIPTION = """
Search Metro Manila (NCR) by landmark, street, house number, barangay or city.
Names are matched with fuzzy (trigram) similarity, so small spelling differences still match.
Each result set returns at most 20 features as GeoJSON (WGS84, longitude/latitude).

**Which results you get depends on which parameters you send:**

| You send | You get (key in `results`) |
|---|---|
| `landmark` (optionally with `brgy`, `city`, `street`) | `landmark`: matching landmarks, each with its barangay/city/province and nearest streets |
| `hn` (optionally with `street`, `subd`, `brgy`, `city`) | `hn`: matching house numbers |
| `street` only, or with `brgy` / `city` | `street`: matching road segments |
| `brgy` and/or `city` only | `admin`: matching barangay boundaries |

Only part of the NCR data is loaded, so some addresses, streets and landmarks will not be found.
The server runs on a free instance, so the first request after a quiet period can take up to a minute.
"""

_EXAMPLE_RESPONSE = {
    "results": {
        "landmark": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": 1001,
                    "geometry": {"type": "Point", "coordinates": [121.05, 14.52]},
                    "properties": {
                        "name": "Example Landmark",
                        "admin": {
                            "city": "Example City",
                            "barangay": "Example Barangay",
                            "province": "Metro Manila",
                        },
                        "nearest_streets": [
                            {"name": "Example Street", "distance_m": 12.4}
                        ],
                    },
                }
            ],
        }
    }
}

search_schema = extend_schema(
    summary="Search landmarks, house numbers, streets and boundaries",
    description=DESCRIPTION,
    parameters=[
        _param("landmark", "Landmark name (fuzzy match).", "Jollibee"),
        _param("hn", "House number, e.g. `B34 L20`. A letter suffix matches (`145` finds `145A`), a longer number does not (`145` skips `1450`).", "B34"),
        _param("street", "Street name (fuzzy match). Suffixes such as Street or Ave are ignored.", "Block 33 - Block 34 Road"),
        _param("subd", "Subdivision name (fuzzy match). Used with `hn`.", "C-5 Pinagsama Phase II"),
        _param("brgy", "Barangay name (fuzzy match).", "Pinagsama"),
        _param("city", "City or municipality name (fuzzy match).", "Taguig"),
    ],
    responses={200: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Landmark search (illustrative values)",
            value=_EXAMPLE_RESPONSE,
            response_only=True,
            status_codes=["200"],
        )
    ],
)
