"""
search/hexgrid.py

Hexagon density grid. PostGIS builds equal-area hexagons (ST_HexagonGrid) over the
loaded barangays and counts the points inside each one, so density is not distorted
by uneven barangay sizes.

    GET /api/analysis/hexgrid/?layer=landmarks&size=500
        layer: landmarks | addresses      size: hexagon edge length in metres (250, 500, 1000, 2000)
"""
import json
import math

from django.core.cache import cache
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import quantile_breaks
from .models import Barangay, HouseNumber, Landmark

LAYERS = {"landmarks": (Landmark, "Landmarks"), "addresses": (HouseNumber, "House numbers")}
SIZES = (250, 500, 1000, 2000)
UTM_51N = 32651            # metric CRS that covers Metro Manila, so hexagons are true metres
HEX_AREA_FACTOR = 3 * math.sqrt(3) / 2   # area of a regular hexagon = factor * edge^2
CACHE_SECONDS = 3600
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


def build(layer, size):
    model, _ = LAYERS[layer]
    barangay_table = Barangay._meta.db_table
    point_table = model._meta.db_table
    # Hexagons are generated first and then probe the points' spatial index,
    # which keeps this fast even for 50,000 points.
    sql = f"""
        WITH ext AS (
            SELECT ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, 4326), {UTM_51N}) AS e
            FROM {barangay_table}
        ),
        grid AS (
            SELECT hg.i, hg.j, ST_Transform(hg.geom, 4326) AS geom
            FROM ext, ST_HexagonGrid(%s, ext.e) AS hg
        )
        SELECT ST_AsGeoJSON(g.geom, 6), COUNT(*)
        FROM grid g
        JOIN {point_table} p ON ST_Intersects(p.geom, g.geom)
        GROUP BY g.i, g.j, g.geom
    """
    with connection.cursor() as cur:
        cur.execute(sql, [float(size)])
        rows = cur.fetchall()

    area_km2 = HEX_AREA_FACTOR * size * size / 1_000_000.0
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(gj),
            "properties": {"count": n, "density": round(n / area_km2, 1)},
        }
        for gj, n in rows
    ]
    counts = sorted(f["properties"]["count"] for f in features)
    return {
        "layer": layer,
        "label": LAYERS[layer][1],
        "size_m": size,
        "hex_area_km2": round(area_km2, 3),
        "hexagons": len(features),
        "total": sum(counts),
        "min": counts[0] if counts else None,
        "max": counts[-1] if counts else None,
        "breaks": quantile_breaks(counts),   # 4 thresholds -> 5 classes
        "note": NOTE,
        "data": {"type": "FeatureCollection", "features": features},
    }


class HexGridView(APIView):
    @extend_schema(
        summary="Hexagon density grid of landmarks or house numbers",
        parameters=[
            OpenApiParameter("layer", OpenApiTypes.STR, enum=list(LAYERS), description="Default: landmarks."),
            OpenApiParameter("size", OpenApiTypes.INT, enum=list(SIZES),
                             description="Hexagon edge length in metres. Default: 500."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        layer = request.query_params.get("layer", "landmarks")
        if layer not in LAYERS:
            raise ParseError(f"Unknown layer '{layer}'. Choose from: {', '.join(LAYERS)}")
        try:
            size = int(request.query_params.get("size", 500))
        except ValueError:
            raise ParseError("size must be a whole number of metres.")
        if size not in SIZES:
            raise ParseError(f"size must be one of: {', '.join(map(str, SIZES))}")

        key = f"hexgrid:{layer}:{size}"
        result = cache.get(key)
        if result is None:
            result = build(layer, size)
            cache.set(key, result, CACHE_SECONDS)
        return Response(result)
