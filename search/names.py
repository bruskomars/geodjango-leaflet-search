"""
search/names.py

Landmark name analysis: keyword categories (schools, churches, ...), names shared by
several landmarks (chains and branches) and the most common words in landmark names.

    GET /api/analysis/names/                          summary
    GET /api/analysis/names/points/?category=schools  points to plot (or ?chain=Jollibee, or ?word=church)
"""
import re

from django.core.cache import cache
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Landmark

# key: (label, regex). Matching is case-insensitive and anchored to the start of a word.
# A landmark can match several categories, so the counts do not add up to the total.
CATEGORIES = {
    "schools": ("Schools", r"\y(?:school|academy|college|university|elementary|institute|learning center|montessori|kindergarten)"),
    "religious": ("Churches and religious sites", r"\y(?:church|chapel|parish|cathedral|mosque|iglesia|ministries|kingdom hall|temple|shrine|diocese)"),
    "health": ("Health and pharmacy", r"\y(?:hospital|clinic|medical|dental|pharmacy|drugstore|health center|laborator|diagnostic|mercury drug|watsons|optical)"),
    "food": ("Food and drink", r"\y(?:restaurant|cafe|coffee|bakery|grill|pizza|burger|jollibee|mcdonald|kitchen|eatery|carinderia|resto|diner|food|tea|chicken|noodle|bbq)"),
    "retail": ("Shops and services", r"\y(?:store|mart|market|supermarket|shop|boutique|mall|grocery|pawnshop|salon|barber|laundry|trading|enterprises)"),
    "finance": ("Banks and finance", r"\y(?:bank|atm|lending|financing|remittance|cooperative|credit|insurance)"),
    "lodging": ("Hotels and lodging", r"\y(?:hotel|inn|resort|hostel|lodge|apartelle|pension|motel|dormitory|condominium)"),
    "government": ("Government and public services", r"\y(?:barangay hall|city hall|municipal|police|fire station|court|post office|bureau|department of|office of)"),
    "auto": ("Fuel and auto", r"\y(?:gas|petron|shell|caltex|seaoil|phoenix|auto|motor|car wash|repair|vulcanizing|parking)"),
    "recreation": ("Sports and recreation", r"\y(?:gym|fitness|park|basketball|playground|sports|spa|cinema|arcade|billiards)"),
}
STOPWORDS = [
    "the", "and", "of", "inc", "co", "corp", "ltd", "llc", "for", "sa", "ng", "at", "ang",
    "mga", "de", "del", "la", "las", "los", "el", "branch", "ph",
]
POINT_LIMIT = 3000
CACHE_SECONDS = 3600
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


def summary():
    table = Landmark._meta.db_table
    keys = list(CATEGORIES)
    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE name IS NULL OR TRIM(name) = ''),
                       COUNT(DISTINCT LOWER(TRIM(name)))
                FROM {table}"""
        )
        total, unnamed, distinct = cur.fetchone()

        filters = ", ".join("COUNT(*) FILTER (WHERE name ~* %s)" for _ in keys)
        cur.execute(f"SELECT {filters} FROM {table}", [CATEGORIES[k][1] for k in keys])
        counts = cur.fetchone()

        cur.execute(
            f"""SELECT MIN(name), COUNT(*) FROM {table}
                WHERE name IS NOT NULL AND TRIM(name) <> ''
                GROUP BY LOWER(TRIM(name)) HAVING COUNT(*) > 1
                ORDER BY 2 DESC, 1 LIMIT 15"""
        )
        chains = [{"name": n, "count": c} for n, c in cur.fetchall()]

        cur.execute(
            f"""SELECT w, COUNT(DISTINCT id) FROM (
                    SELECT id, regexp_split_to_table(LOWER(name), '[^a-z0-9ñ]+') AS w
                    FROM {table} WHERE name IS NOT NULL
                ) t
                WHERE LENGTH(w) > 2 AND w !~ '^[0-9]+$' AND w <> ALL(%s)
                GROUP BY w ORDER BY 2 DESC, 1 LIMIT 24""",
            [STOPWORDS],
        )
        words = [{"word": w, "count": c} for w, c in cur.fetchall()]

    categories = sorted(
        ({"key": k, "label": CATEGORIES[k][0], "count": n} for k, n in zip(keys, counts)),
        key=lambda c: -c["count"],
    )
    repeated = sum(c["count"] for c in chains)
    return {
        "note": NOTE,
        "total": total,
        "unnamed": unnamed,
        "distinct_names": distinct,
        "categories": categories,
        "chains": chains,
        "words": words,
        "repeated_in_top": repeated,
    }


class NameSummaryView(APIView):
    @extend_schema(summary="Landmark name analysis: categories, repeated names, common words",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        data = cache.get("names:summary")
        if data is None:
            data = summary()
            cache.set("names:summary", data, CACHE_SECONDS)
        return Response(data)


class NamePointsView(APIView):
    @extend_schema(
        summary="Landmarks matching a category, a repeated name, or a word (for plotting)",
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, enum=list(CATEGORIES)),
            OpenApiParameter("chain", OpenApiTypes.STR, description="Exact landmark name, e.g. one chain."),
            OpenApiParameter("word", OpenApiTypes.STR, description="A word that appears in the name."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        params = request.query_params
        given = [k for k in ("category", "chain", "word") if params.get(k)]
        if len(given) != 1:
            raise ParseError("Send exactly one of: category, chain, word.")
        kind = given[0]
        value = params[kind].strip()

        if kind == "category":
            if value not in CATEGORIES:
                raise ParseError(f"Unknown category. Choose from: {', '.join(CATEGORIES)}")
            label, condition, arg = CATEGORIES[value][0], "name ~* %s", CATEGORIES[value][1]
        elif kind == "chain":
            if len(value) > 120:
                raise ParseError("chain is too long.")
            label, condition, arg = value, "LOWER(TRIM(name)) = LOWER(TRIM(%s))", value
        else:
            if not re.fullmatch(r"[\w\-ñÑ]{2,40}", value):
                raise ParseError("word must be 2 to 40 letters or digits.")
            label, condition, arg = value, "name ~* %s", rf"\y{re.escape(value)}\y"

        table = Landmark._meta.db_table
        with connection.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {condition}", [arg])
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT name, ST_X(geom), ST_Y(geom) FROM {table} WHERE {condition} LIMIT %s",
                [arg, POINT_LIMIT],
            )
            rows = cur.fetchall()

        features = [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]},
             "properties": {"name": n or "(unnamed)"}}
            for n, x, y in rows
        ]
        return Response({
            "label": label,
            "count": total,
            "shown": len(features),
            "data": {"type": "FeatureCollection", "features": features},
        })
