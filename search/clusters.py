"""
search/clusters.py

Hotspot detection with DBSCAN (PostGIS ST_ClusterDBSCAN): points that sit within `eps`
metres of each other, in groups of at least `min_points`, form a cluster. Isolated
points are left out as noise.

    GET /api/analysis/clusters/?layer=landmarks&eps=100&min_points=10
        layer: landmarks | addresses     eps: 50, 100, 200, 300 (metres)     min_points: 5, 10, 20
"""
import json

from django.core.cache import cache
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Barangay, HouseNumber, Landmark

# layer: (model, column used for "most common name", label)
LAYERS = {
    "landmarks": (Landmark, "name", "Landmarks"),
    "addresses": (HouseNumber, "street_name", "House numbers"),
}
EPS_OPTIONS = (50, 100, 200, 300)
MIN_POINTS_OPTIONS = (5, 10, 20)
TOP_CLUSTERS = 50          # clusters returned with geometry
UTM_51N = 32651            # metric CRS for Metro Manila, so eps is in true metres
CACHE_SECONDS = 3600
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


def build(layer, eps, min_points):
    model, name_col, label = LAYERS[layer]
    table = model._meta.db_table
    barangay = Barangay._meta.db_table
    # Table and column names come from the constants above, never from user input
    sql = f"""
        WITH pts AS (
            SELECT geom, {name_col} AS nm, ST_Transform(geom, {UTM_51N}) AS g FROM {table}
        ),
        clustered AS (
            SELECT geom, nm, ST_ClusterDBSCAN(g, %s, %s) OVER () AS cid FROM pts
        ),
        agg AS (
            SELECT cid, COUNT(*) AS n, ST_Collect(geom) AS c,
                   mode() WITHIN GROUP (ORDER BY nm) FILTER (WHERE nm IS NOT NULL) AS top_name
            FROM clustered WHERE cid IS NOT NULL GROUP BY cid
        ),
        ranked AS (
            SELECT cid, n, top_name,
                   ROW_NUMBER() OVER (ORDER BY n DESC, cid) AS rk,
                   ST_Buffer(ST_ConvexHull(c)::geography, 25)::geometry AS hull,
                   ST_Centroid(c) AS cent
            FROM agg
        )
        SELECT r.rk, r.n, r.top_name,
               CASE WHEN r.rk <= %s THEN ST_AsGeoJSON(r.hull, 6) END,
               ST_Area(r.hull::geography) / 1000000.0,
               ST_X(r.cent), ST_Y(r.cent), b.name, b.city
        FROM ranked r
        LEFT JOIN {barangay} b ON ST_Contains(b.geom, r.cent)
        ORDER BY r.rk
    """
    with connection.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        total_points = cur.fetchone()[0]
        cur.execute(sql, [float(eps), int(min_points), TOP_CLUSTERS])
        rows = cur.fetchall()

    seen = set()
    features = []
    cluster_count = 0
    clustered_points = 0
    for rk, n, top_name, geojson, area_km2, lng, lat, b_name, b_city in rows:
        if rk in seen:          # a centroid on a shared boundary can match two barangays
            continue
        seen.add(rk)
        cluster_count += 1
        clustered_points += n
        if geojson is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": json.loads(geojson),
            "properties": {
                "rank": rk,
                "count": n,
                "area_km2": round(area_km2, 3),
                "density": round(n / area_km2, 1) if area_km2 else None,
                "top_name": top_name,
                "barangay": b_name,
                "city": b_city,
                "lat": lat,
                "lng": lng,
            },
        })

    return {
        "layer": layer,
        "label": label,
        "name_label": "Most common name" if layer == "landmarks" else "Most common street",
        "eps_m": eps,
        "min_points": min_points,
        "points": total_points,
        "clusters": cluster_count,
        "clustered_points": clustered_points,
        "isolated_points": total_points - clustered_points,
        "shown": len(features),
        "note": NOTE,
        "data": {"type": "FeatureCollection", "features": features},
    }


class ClustersView(APIView):
    @extend_schema(
        summary="Hotspot clusters of landmarks or house numbers (DBSCAN)",
        parameters=[
            OpenApiParameter("layer", OpenApiTypes.STR, enum=list(LAYERS), description="Default: landmarks."),
            OpenApiParameter("eps", OpenApiTypes.INT, enum=list(EPS_OPTIONS),
                             description="Maximum distance in metres between neighbouring points. Default: 100."),
            OpenApiParameter("min_points", OpenApiTypes.INT, enum=list(MIN_POINTS_OPTIONS),
                             description="Minimum points to form a cluster. Default: 10."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        params = request.query_params
        layer = params.get("layer", "landmarks")
        if layer not in LAYERS:
            raise ParseError(f"Unknown layer '{layer}'. Choose from: {', '.join(LAYERS)}")
        try:
            eps = int(params.get("eps", 100))
            min_points = int(params.get("min_points", 10))
        except ValueError:
            raise ParseError("eps and min_points must be whole numbers.")
        if eps not in EPS_OPTIONS:
            raise ParseError(f"eps must be one of: {', '.join(map(str, EPS_OPTIONS))}")
        if min_points not in MIN_POINTS_OPTIONS:
            raise ParseError(f"min_points must be one of: {', '.join(map(str, MIN_POINTS_OPTIONS))}")

        key = f"clusters:{layer}:{eps}:{min_points}"
        result = cache.get(key)
        if result is None:
            result = build(layer, eps, min_points)
            cache.set(key, result, CACHE_SECONDS)
        return Response(result)
