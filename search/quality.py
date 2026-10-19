"""
search/quality.py

Data quality checks, computed live (simple aggregates, no precomputed table needed).

    GET /api/analysis/quality/                          whole database
    GET /api/analysis/quality/?city=City of Taguig      one city
    GET /api/analysis/quality/?city=...&barangay=...    one barangay (needs city: names repeat)
    GET /api/analysis/areas/                            cities and barangays, for filter dropdowns
"""
from django.db.models import Count, Exists, Min, OuterRef, Q, Sum
from django.db.models.functions import Lower, Trim
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Barangay, HouseNumber, Landmark, Road
from .summary_models import BarangaySummary

NOTE = "Figures describe the data loaded in this demo (a random sample), not complete NCR coverage."

ADDRESS_FIELDS = {
    "house_number": "House number",
    "street_name": "Street name",
    "subdivision": "Subdivision",
    "barangay": "Barangay",
    "municipality": "Municipality",
}


def blank(field):
    """Matches rows where the field is NULL or only whitespace."""
    return Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__regex": r"^\s*$"})


def pct(part, total):
    return round(100.0 * part / total, 1) if total else 0.0


class DataQualityView(APIView):
    @extend_schema(
        summary="Data completeness, duplicate names and coverage checks",
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR,
                             description="Limit the checks to one city, e.g. City of Taguig."),
            OpenApiParameter("barangay", OpenApiTypes.STR,
                             description="Limit to one barangay (requires city)."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        city = request.query_params.get("city", "").strip()
        barangay = request.query_params.get("barangay", "").strip()
        if barangay and not city:
            raise ParseError("barangay requires city, because barangay names repeat across cities.")

        # Selected area: points count when inside its boundaries, roads when they touch them
        roads_qs, hn_qs, lm_qs = Road.objects.all(), HouseNumber.objects.all(), Landmark.objects.all()
        summary_qs = BarangaySummary.objects.all()
        area = None
        if city:
            areas = Barangay.objects.filter(city__iexact=city)
            area = {"city": city, "barangay": barangay or None, "label": city}
            if barangay:
                areas = areas.filter(name__iexact=barangay)
                area["label"] = f"{barangay}, {city}"
            if not areas.exists():
                raise NotFound("No barangays match that city/barangay.")
            roads_qs = roads_qs.filter(Exists(areas.filter(geom__intersects=OuterRef("geom"))))
            hn_qs = hn_qs.filter(Exists(areas.filter(geom__contains=OuterRef("geom"))))
            lm_qs = lm_qs.filter(Exists(areas.filter(geom__contains=OuterRef("geom"))))
            summary_qs = summary_qs.filter(barangay__in=areas)

        # Roads
        r = roads_qs.aggregate(total=Count("id"), unnamed=Count("id", filter=blank("name")))

        # House numbers: how many rows are missing each field
        agg = {"total": Count("id")}
        for field in ADDRESS_FIELDS:
            agg[f"missing_{field}"] = Count("id", filter=blank(field))
        h = hn_qs.aggregate(**agg)

        # Landmarks: unnamed, and names that appear more than once (chains, branches, duplicates)
        lm_total = lm_qs.count()
        lm_unnamed = lm_qs.filter(blank("name")).count()
        groups = list(
            lm_qs.exclude(blank("name"))
            .annotate(key=Lower(Trim("name")))
            .values("key")
            .annotate(n=Count("id"), label=Min("name"))
            .filter(n__gt=1)
            .order_by("-n", "key")
        )

        # Coverage, from the barangay summary table
        cov = summary_qs.aggregate(
            barangays=Count("id"),
            no_landmarks=Count("id", filter=Q(landmark_count=0)),
            no_addresses=Count("id", filter=Q(address_count=0)),
            no_roads=Count("id", filter=Q(road_km=0)),
            landmarks_inside=Sum("landmark_count"),
            addresses_inside=Sum("address_count"),
        )
        n_brgy = cov["barangays"]
        have_summary = n_brgy > 0
        check_outside = have_summary and area is None  # only meaningful for the whole database

        return Response({
            "note": NOTE,
            "area": area,
            "roads": {
                "total": r["total"],
                "unnamed": r["unnamed"],
                "unnamed_pct": pct(r["unnamed"], r["total"]),
            },
            "addresses": {
                "total": h["total"],
                "fields": [
                    {
                        "field": label,
                        "missing": h[f"missing_{key}"],
                        "missing_pct": pct(h[f"missing_{key}"], h["total"]),
                    }
                    for key, label in ADDRESS_FIELDS.items()
                ],
            },
            "landmarks": {
                "total": lm_total,
                "unnamed": lm_unnamed,
                "unnamed_pct": pct(lm_unnamed, lm_total),
                "duplicate_names": len(groups),
                "landmarks_sharing_a_name": sum(g["n"] for g in groups),
                "top_repeated": [{"name": g["label"], "count": g["n"]} for g in groups[:10]],
            },
            "coverage": {
                "summary_available": have_summary,
                "barangays": n_brgy,
                "no_landmarks": cov["no_landmarks"],
                "no_landmarks_pct": pct(cov["no_landmarks"], n_brgy),
                "no_addresses": cov["no_addresses"],
                "no_addresses_pct": pct(cov["no_addresses"], n_brgy),
                "no_roads": cov["no_roads"],
                "no_roads_pct": pct(cov["no_roads"], n_brgy),
                # Points that fall inside no barangay boundary (should be 0)
                "landmarks_outside": (lm_total - (cov["landmarks_inside"] or 0)) if check_outside else None,
                "addresses_outside": (h["total"] - (cov["addresses_inside"] or 0)) if check_outside else None,
            },
        })


class AreasView(APIView):
    @extend_schema(
        summary="Cities and their barangays (for filter dropdowns)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        cities = {}
        rows = (
            Barangay.objects.exclude(city__isnull=True).exclude(name__isnull=True)
            .order_by("city", "name").values_list("city", "name")
        )
        for city, name in rows:
            cities.setdefault(city, set()).add(name)
        return Response({
            "cities": [{"name": c, "barangays": sorted(names)} for c, names in cities.items()]
        })
