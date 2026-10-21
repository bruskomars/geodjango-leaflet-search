"""
search/roadstats.py

Road network statistics: totals, street types, longest streets, most fragmented
street names and the barangays with the most road.

    GET /api/analysis/roads/                              summary
    GET /api/analysis/roads/geometry/?street=Rizal Avenue (or ?type=Avenue)   segments to plot
"""
import json

from django.core.cache import cache
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Road
from .summary_models import BarangaySummary

CACHE_SECONDS = 3600
GEOMETRY_LIMIT = 3000
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."

# Full street name as shown on the search map: prefix type + name + suffix
FULL_NAME = "CONCAT_WS(' ', NULLIF(TRIM(prefix_type), ''), TRIM(name), NULLIF(TRIM(suffix_type), ''))"
TYPE_EXPR = "COALESCE(NULLIF(TRIM(prefix_type), ''), '(none)')"
LENGTH_KM = "ST_Length(geom::geography) / 1000.0"
NAMED = "name IS NOT NULL AND TRIM(name) <> ''"


def summary():
    table = Road._meta.db_table
    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE NOT ({NAMED})),
                       COALESCE(SUM({LENGTH_KM}), 0),
                       COUNT(DISTINCT LOWER({FULL_NAME})) FILTER (WHERE {NAMED})
                FROM {table}"""
        )
        segments, unnamed, km, distinct = cur.fetchone()

        cur.execute(
            f"""SELECT {TYPE_EXPR}, COUNT(*), SUM({LENGTH_KM})
                FROM {table} GROUP BY 1 ORDER BY 3 DESC LIMIT 10"""
        )
        types = [{"type": t, "segments": n, "km": round(k, 1)} for t, n, k in cur.fetchall()]

        base = f"""SELECT MIN({FULL_NAME}), COUNT(*), SUM({LENGTH_KM}) AS km
                   FROM {table} WHERE {NAMED}
                   GROUP BY LOWER({FULL_NAME})"""
        cur.execute(f"{base} ORDER BY km DESC LIMIT 15")
        longest = [{"name": n, "segments": s, "km": round(k, 2)} for n, s, k in cur.fetchall()]
        cur.execute(f"{base} ORDER BY COUNT(*) DESC, km DESC LIMIT 10")
        fragmented = [{"name": n, "segments": s, "km": round(k, 2)} for n, s, k in cur.fetchall()]

    def barangay_rows(order):
        rows = BarangaySummary.objects.select_related("barangay").order_by(order)[:10]
        return [
            {"name": r.barangay.name, "city": r.barangay.city,
             "road_km": round(r.road_km, 1), "road_density": r.road_density}
            for r in rows
        ]

    return {
        "note": NOTE,
        "totals": {
            "segments": segments,
            "km": round(km, 1),
            "unnamed": unnamed,
            "unnamed_pct": round(100.0 * unnamed / segments, 1) if segments else 0.0,
            "distinct_names": distinct,
            "avg_segment_m": round(km * 1000.0 / segments) if segments else 0,
        },
        "types": types,
        "longest": longest,
        "fragmented": fragmented,
        "barangays_by_km": barangay_rows("-road_km"),
        "barangays_by_density": barangay_rows_by_density(),
    }


def barangay_rows_by_density():
    # road_density is a property (road_km / area_km2), so rank in Python
    rows = sorted(BarangaySummary.objects.select_related("barangay"), key=lambda r: -r.road_density)[:10]
    return [
        {"name": r.barangay.name, "city": r.barangay.city,
         "road_km": round(r.road_km, 1), "road_density": r.road_density}
        for r in rows
    ]


class RoadSummaryView(APIView):
    @extend_schema(summary="Road network statistics", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        data = cache.get("roads:summary")
        if data is None:
            data = summary()
            cache.set("roads:summary", data, CACHE_SECONDS)
        return Response(data)


class RoadGeometryView(APIView):
    @extend_schema(
        summary="Road segments of one street name or one street type (for plotting)",
        parameters=[
            OpenApiParameter("street", OpenApiTypes.STR, description="Full street name, e.g. Rizal Avenue."),
            OpenApiParameter("type", OpenApiTypes.STR, description="Street type, e.g. Avenue."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        params = request.query_params
        given = [k for k in ("street", "type") if params.get(k)]
        if len(given) != 1:
            raise ParseError("Send exactly one of: street, type.")
        kind = given[0]
        value = params[kind].strip()
        if len(value) > 200:
            raise ParseError(f"{kind} is too long.")

        if kind == "street":
            condition = f"{NAMED} AND LOWER({FULL_NAME}) = LOWER(%s)"
        else:
            condition = f"{TYPE_EXPR} = %s"

        table = Road._meta.db_table
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*), COALESCE(SUM({LENGTH_KM}), 0) FROM {table} WHERE {condition}", [value]
            )
            count, km = cur.fetchone()
            cur.execute(
                f"""SELECT {FULL_NAME}, ST_AsGeoJSON(geom, 5) FROM {table}
                    WHERE {condition} LIMIT %s""",
                [value, GEOMETRY_LIMIT],
            )
            rows = cur.fetchall()

        features = [
            {"type": "Feature", "geometry": json.loads(gj), "properties": {"name": n or "(unnamed)"}}
            for n, gj in rows
        ]
        return Response({
            "label": value,
            "segments": count,
            "km": round(km, 2),
            "shown": len(features),
            "data": {"type": "FeatureCollection", "features": features},
        })
