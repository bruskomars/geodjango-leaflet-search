"""
search/consistency.py

Address consistency check: does the barangay and municipality written on each house
number match the barangay boundary the point actually falls in? Names are compared with
trigram similarity, so small spelling differences do not count as mismatches.

    GET /api/analysis/consistency/?strictness=normal      lenient | normal | strict
"""
from django.core.cache import cache
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Barangay, HouseNumber

# Minimum name similarity (0 to 1) for the declared and actual name to count as a match
STRICTNESS = {"lenient": 0.3, "normal": 0.5, "strict": 0.8}
POINT_LIMIT = 2000
PAIR_LIMIT = 15
CACHE_SECONDS = 3600
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


def _joined():
    """Each house number joined to the barangay boundary that contains it."""
    return f"""
        SELECT h.house_number, h.street_name, h.geom,
               h.barangay AS decl_b, h.municipality AS decl_m,
               b.name AS act_b, b.city AS act_c,
               similarity(LOWER(COALESCE(h.barangay, '')), LOWER(COALESCE(b.name, ''))) AS sb,
               similarity(LOWER(COALESCE(h.municipality, '')), LOWER(COALESCE(b.city, ''))) AS sm
        FROM {HouseNumber._meta.db_table} h
        LEFT JOIN {Barangay._meta.db_table} b ON ST_Contains(b.geom, h.geom)
    """


HAS_B = "act_b IS NOT NULL AND TRIM(COALESCE(decl_b, '')) <> ''"
HAS_M = "act_b IS NOT NULL AND TRIM(COALESCE(decl_m, '')) <> ''"


def _pct(part, total):
    return round(100.0 * part / total, 1) if total else 0.0


def build(strictness):
    threshold = STRICTNESS[strictness]
    joined = _joined()
    with connection.cursor() as cur:
        cur.execute(
            f"""WITH j AS ({joined})
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE act_b IS NULL),
                       COUNT(*) FILTER (WHERE act_b IS NOT NULL AND TRIM(COALESCE(decl_b, '')) = ''),
                       COUNT(*) FILTER (WHERE {HAS_B} AND sb >= %s),
                       COUNT(*) FILTER (WHERE {HAS_B} AND sb < %s),
                       COUNT(*) FILTER (WHERE act_b IS NOT NULL AND TRIM(COALESCE(decl_m, '')) = ''),
                       COUNT(*) FILTER (WHERE {HAS_M} AND sm >= %s),
                       COUNT(*) FILTER (WHERE {HAS_M} AND sm < %s)
                FROM j""",
            [threshold] * 4,
        )
        (total, outside, b_missing, b_match, b_mismatch,
         m_missing, m_match, m_mismatch) = cur.fetchone()

        cur.execute(
            f"""WITH j AS ({joined})
                SELECT decl_b, act_b, act_c, COUNT(*) FROM j
                WHERE {HAS_B} AND sb < %s
                GROUP BY decl_b, act_b, act_c ORDER BY 4 DESC, 1 LIMIT %s""",
            [threshold, PAIR_LIMIT],
        )
        pairs = [
            {"declared": d, "actual": a, "city": c, "count": n} for d, a, c, n in cur.fetchall()
        ]

        cur.execute(
            f"""WITH j AS ({joined})
                SELECT house_number, street_name, decl_b, act_b, act_c, ST_X(geom), ST_Y(geom)
                FROM j WHERE {HAS_B} AND sb < %s LIMIT %s""",
            [threshold, POINT_LIMIT],
        )
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [x, y]},
                "properties": {
                    "house_number": hn, "street": sn, "declared": d, "actual": a, "city": c,
                },
            }
            for hn, sn, d, a, c, x, y in cur.fetchall()
        ]

    def block(missing, match, mismatch):
        return {
            "missing": missing, "match": match, "mismatch": mismatch,
            "match_pct": _pct(match, total), "mismatch_pct": _pct(mismatch, total),
            "missing_pct": _pct(missing, total),
        }

    return {
        "note": NOTE,
        "strictness": strictness,
        "threshold": threshold,
        "total": total,
        "outside": outside,
        "outside_pct": _pct(outside, total),
        "barangay": block(b_missing, b_match, b_mismatch),
        "municipality": block(m_missing, m_match, m_mismatch),
        "top_pairs": pairs,
        "points": {
            "count": b_mismatch,
            "shown": len(features),
            "data": {"type": "FeatureCollection", "features": features},
        },
    }


class ConsistencyView(APIView):
    @extend_schema(
        summary="Declared vs actual barangay and municipality of house numbers",
        parameters=[
            OpenApiParameter("strictness", OpenApiTypes.STR, enum=list(STRICTNESS),
                             description="How similar two names must be to match. Default: normal."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        strictness = request.query_params.get("strictness", "normal")
        if strictness not in STRICTNESS:
            raise ParseError(f"strictness must be one of: {', '.join(STRICTNESS)}")
        key = f"consistency:{strictness}"
        data = cache.get(key)
        if data is None:
            data = build(strictness)
            cache.set(key, data, CACHE_SECONDS)
        return Response(data)
