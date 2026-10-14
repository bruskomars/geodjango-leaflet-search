"""
search/analysis.py

Choropleth data: one GeoJSON feature per barangay, with the chosen metric,
legend breaks, totals and a top-10 ranking.

    GET /api/analysis/barangays/?metric=landmark_density
    GET /api/analysis/barangays/?metric=road_km&city=City of Taguig
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .summary_models import BarangaySummary

METRICS = {
    "landmark_density": "Landmarks per km²",
    "address_density": "House numbers per km²",
    "road_density": "Road km per km²",
    "landmark_count": "Landmarks",
    "address_count": "House numbers",
    "road_km": "Road length (km)",
    "area_km2": "Area (km²)",
}

NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."


class BarangaySummarySerializer(GeoFeatureModelSerializer):
    id = serializers.IntegerField(source="barangay.src_id", read_only=True)
    name = serializers.CharField(source="barangay.name", read_only=True)
    city = serializers.CharField(source="barangay.city", read_only=True)
    region = serializers.CharField(source="barangay.region", read_only=True)
    landmark_density = serializers.FloatField(read_only=True)
    address_density = serializers.FloatField(read_only=True)
    road_density = serializers.FloatField(read_only=True)

    class Meta:
        model = BarangaySummary
        geo_field = "geom_simple"
        id_field = False
        fields = [
            "id", "name", "city", "region", "area_km2",
            "landmark_count", "address_count", "road_km",
            "landmark_density", "address_density", "road_density",
        ]


def quantile_breaks(values, classes=5):
    """Upper thresholds that split sorted values into equal-count classes."""
    n = len(values)
    if not n:
        return []
    return [values[min(n - 1, (n * i) // classes)] for i in range(1, classes)]


class BarangaySummaryView(APIView):
    @extend_schema(
        summary="Per-barangay statistics for a choropleth map",
        parameters=[
            OpenApiParameter("metric", OpenApiTypes.STR, enum=list(METRICS),
                             description="Value to map. Default: landmark_density."),
            OpenApiParameter("city", OpenApiTypes.STR,
                             description="Only barangays of this city, e.g. City of Taguig."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        metric = request.query_params.get("metric", "landmark_density")
        if metric not in METRICS:
            raise ParseError(f"Unknown metric '{metric}'. Choose from: {', '.join(METRICS)}")

        rows = BarangaySummary.objects.select_related("barangay")
        city = request.query_params.get("city")
        if city:
            rows = rows.filter(barangay__city__iexact=city)
        rows = list(rows)

        values = sorted(getattr(r, metric) for r in rows)
        top = sorted(rows, key=lambda r: getattr(r, metric), reverse=True)[:10]

        return Response({
            "metric": metric,
            "label": METRICS[metric],
            "note": NOTE,
            "count": len(rows),
            "min": values[0] if values else None,
            "max": values[-1] if values else None,
            "breaks": quantile_breaks(values),   # 4 thresholds -> 5 classes
            "totals": {
                "landmarks": sum(r.landmark_count for r in rows),
                "addresses": sum(r.address_count for r in rows),
                "road_km": round(sum(r.road_km for r in rows), 1),
                "area_km2": round(sum(r.area_km2 for r in rows), 1),
            },
            "top": [
                {"name": r.barangay.name, "city": r.barangay.city, "value": getattr(r, metric)}
                for r in top
            ],
            "data": BarangaySummarySerializer(rows, many=True).data,
        })
