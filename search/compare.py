"""
search/compare.py

Compare two areas side by side. Each area is a whole city, or one barangay within a city.

    GET /api/analysis/compare/?a_city=City of Taguig&b_city=Quezon City
    GET /api/analysis/compare/?a_city=City of Taguig&a_barangay=Pinagsama&b_city=Quezon City
"""
import json

from django.db.models import Count, Exists, OuterRef, Q, Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Barangay, Landmark
from .names import CATEGORIES
from .summary_models import BarangaySummary

NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


def _per_km2(value, area):
    return round(value / area, 2) if area else 0.0


def area_stats(city, barangay):
    areas = Barangay.objects.filter(city__iexact=city)
    label = city
    if barangay:
        areas = areas.filter(name__iexact=barangay)
        label = f"{barangay}, {city}"
    if not areas.exists():
        raise NotFound(f"No barangays match '{label}'.")

    summaries = BarangaySummary.objects.filter(barangay__in=areas)
    totals = summaries.aggregate(
        area=Sum("area_km2"), landmarks=Sum("landmark_count"),
        addresses=Sum("address_count"), road_km=Sum("road_km"),
    )
    area_km2 = totals["area"] or 0.0
    landmarks = totals["landmarks"] or 0
    addresses = totals["addresses"] or 0
    road_km = totals["road_km"] or 0.0

    # Landmark counts per keyword category, for landmarks inside the area
    counts = (
        Landmark.objects.filter(Exists(areas.filter(geom__contains=OuterRef("geom"))))
        .aggregate(**{key: Count("id", filter=Q(name__iregex=rx)) for key, (_, rx) in CATEGORIES.items()})
    )
    categories = [
        {"key": key, "label": CATEGORIES[key][0], "count": n, "per_km2": _per_km2(n, area_km2)}
        for key, n in counts.items()
    ]

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(s.geom_simple.geojson),
            "properties": {"name": s.barangay.name},
        }
        for s in summaries.select_related("barangay")
    ]

    return {
        "label": label,
        "barangays": areas.count(),
        "area_km2": round(area_km2, 2),
        "landmarks": landmarks,
        "addresses": addresses,
        "road_km": round(road_km, 1),
        "landmark_density": _per_km2(landmarks, area_km2),
        "address_density": _per_km2(addresses, area_km2),
        "road_density": _per_km2(road_km, area_km2),
        "categories": categories,
        "geometry": {"type": "FeatureCollection", "features": features},
    }


class CompareView(APIView):
    @extend_schema(
        summary="Compare two areas (cities or barangays) side by side",
        parameters=[
            OpenApiParameter("a_city", OpenApiTypes.STR, required=True, description="City of area A."),
            OpenApiParameter("a_barangay", OpenApiTypes.STR, description="Barangay of area A (optional)."),
            OpenApiParameter("b_city", OpenApiTypes.STR, required=True, description="City of area B."),
            OpenApiParameter("b_barangay", OpenApiTypes.STR, description="Barangay of area B (optional)."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        params = request.query_params
        sides = {}
        for side in ("a", "b"):
            city = params.get(f"{side}_city", "").strip()
            if not city:
                raise ParseError(f"{side}_city is required.")
            sides[side] = area_stats(city, params.get(f"{side}_barangay", "").strip())
        return Response({"note": NOTE, **sides})
