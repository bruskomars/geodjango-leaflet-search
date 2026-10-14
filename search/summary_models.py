"""
search/summary_models.py

Pre-computed statistics for each barangay. Filled by `manage.py compute_summary`,
so the API never has to aggregate 70,000 roads on every request.
"""
from django.contrib.gis.db import models


def _ratio(count, area):
    return round(count / area, 2) if area else 0.0


class BarangaySummary(models.Model):
    # String reference, so this module does not need to import models.py
    barangay = models.OneToOneField(
        "search.Barangay", on_delete=models.CASCADE, related_name="summary"
    )
    area_km2 = models.FloatField()
    landmark_count = models.IntegerField(default=0)
    address_count = models.IntegerField(default=0)
    road_km = models.FloatField(default=0)
    # Simplified outline for fast map display (the full polygon stays on Barangay)
    geom_simple = models.MultiPolygonField(srid=4326)
    computed_at = models.DateTimeField()

    @property
    def landmark_density(self):
        return _ratio(self.landmark_count, self.area_km2)

    @property
    def address_density(self):
        return _ratio(self.address_count, self.area_km2)

    @property
    def road_density(self):
        return _ratio(self.road_km, self.area_km2)  # km of road per km2

    def __str__(self):
        return f"Summary for barangay {self.barangay_id}"
