"""
search/radius.py

Radius analysis around a clicked point.

    GET /api/analysis/radius/?lat=14.52&lng=121.05&radius=500     (radius in metres, 50 to 3000)
"""
from django.contrib.gis.geos import Point
from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Barangay, HouseNumber, Landmark, Road

MAX_RADIUS = 3000
LIST_LIMIT = 100   # nearest landmarks returned for plotting
NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."

# Circle of `radius` metres around (lng, lat), built on geography so the size is true metres
CIRCLE = "ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry"
POINT_GEOG = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"


def _number(request, name, low, high, default=None):
    raw = request.query_params.get(name)
    if raw is None:
        if default is None:
            raise ParseError(f"'{name}' is required.")
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ParseError(f"'{name}' must be a number.")
    if not low <= value <= high:
        raise ParseError(f"'{name}' must be between {low} and {high}.")
    return value


class RadiusAnalysisView(APIView):
    @extend_schema(
        summary="Counts, nearest landmarks and road length within a radius of a point",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.FLOAT, required=True, description="Latitude (WGS84)."),
            OpenApiParameter("lng", OpenApiTypes.FLOAT, required=True, description="Longitude (WGS84)."),
            OpenApiParameter("radius", OpenApiTypes.FLOAT,
                             description=f"Radius in metres, 50 to {MAX_RADIUS}. Default 500."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        lat = _number(request, "lat", -90, 90)
        lng = _number(request, "lng", -180, 180)
        radius = _number(request, "radius", 50, MAX_RADIUS, default=500)

        landmark, housenumber, road = (m._meta.db_table for m in (Landmark, HouseNumber, Road))
        circle = [lng, lat, radius]
        centre = [lng, lat]

        with connection.cursor() as cur:
            # Landmarks: total, plus the nearest ones for the map and list
            cur.execute(f"SELECT COUNT(*) FROM {landmark} WHERE ST_Intersects(geom, {CIRCLE})", circle)
            landmark_count = cur.fetchone()[0]
            cur.execute(
                f"""SELECT name, ST_X(geom), ST_Y(geom),
                           ST_Distance(geom::geography, {POINT_GEOG}) AS d
                    FROM {landmark}
                    WHERE ST_Intersects(geom, {CIRCLE})
                    ORDER BY d LIMIT %s""",
                centre + circle + [LIST_LIMIT],
            )
            landmarks = [
                {"name": (n or "(unnamed)"), "lng": x, "lat": y, "distance_m": round(d)}
                for n, x, y, d in cur.fetchall()
            ]

            # House numbers: total and the streets with the most of them
            cur.execute(f"SELECT COUNT(*) FROM {housenumber} WHERE ST_Intersects(geom, {CIRCLE})", circle)
            address_count = cur.fetchone()[0]
            cur.execute(
                f"""SELECT COALESCE(NULLIF(TRIM(street_name), ''), '(no street name)') AS s, COUNT(*)
                    FROM {housenumber}
                    WHERE ST_Intersects(geom, {CIRCLE})
                    GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 8""",
                circle,
            )
            top_streets = [{"name": s, "count": c} for s, c in cur.fetchall()]

            # Roads: length of each street that lies inside the circle
            cur.execute(
                f"""SELECT COALESCE(NULLIF(TRIM(name), ''), '(unnamed)') AS s,
                           COUNT(*) AS segments,
                           SUM(ST_Length(ST_Intersection(geom, {CIRCLE})::geography)) AS metres
                    FROM {road}
                    WHERE ST_Intersects(geom, {CIRCLE})
                    GROUP BY 1 ORDER BY metres DESC""",
                circle + circle,
            )
            road_rows = cur.fetchall()

        barangay = Barangay.objects.filter(geom__contains=Point(lng, lat, srid=4326)).first()

        return Response({
            "note": NOTE,
            "center": {"lat": lat, "lng": lng},
            "radius_m": radius,
            "barangay": {"name": barangay.name, "city": barangay.city} if barangay else None,
            "landmarks": {"count": landmark_count, "shown": len(landmarks), "items": landmarks},
            "addresses": {"count": address_count, "top_streets": top_streets},
            "roads": {
                "segments": sum(r[1] for r in road_rows),
                "km": round(sum(r[2] or 0 for r in road_rows) / 1000.0, 2),
                "top": [{"name": r[0], "metres": round(r[2] or 0)} for r in road_rows[:10]],
            },
        })
