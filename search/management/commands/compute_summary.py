"""
search/management/commands/compute_summary.py

Recomputes the per-barangay summary table. Run it after every data load:
    python manage.py compute_summary
"""
import time

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from search.models import Barangay, HouseNumber, Landmark, Road
from search.summary_models import BarangaySummary

SIMPLIFY_TOLERANCE = 0.0001  # degrees, roughly 11 m: keeps shapes recognisable but light


class Command(BaseCommand):
    help = "Recompute per-barangay counts, road length and area."

    def handle(self, *args, **options):
        # Table names come from the models, never from user input
        summary = BarangaySummary._meta.db_table
        brgy = Barangay._meta.db_table
        landmark = Landmark._meta.db_table
        housenumber = HouseNumber._meta.db_table
        road = Road._meta.db_table

        sql = f"""
            INSERT INTO {summary}
                (barangay_id, area_km2, landmark_count, address_count, road_km,
                 geom_simple, computed_at)
            SELECT
                bg.id,
                ROUND((ST_Area(bg.geom::geography) / 1000000.0)::numeric, 4),
                (SELECT COUNT(*) FROM {landmark} l WHERE ST_Contains(bg.geom, l.geom)),
                (SELECT COUNT(*) FROM {housenumber} h WHERE ST_Contains(bg.geom, h.geom)),
                ROUND((COALESCE((
                    SELECT SUM(ST_Length(
                        ST_Intersection(r.geom, ST_MakeValid(bg.geom))::geography))
                    FROM {road} r
                    WHERE ST_Intersects(r.geom, bg.geom)
                ), 0) / 1000.0)::numeric, 3),
                ST_Multi(ST_SimplifyPreserveTopology(bg.geom, %s)),
                now()
            FROM {brgy} bg
        """

        started = time.time()
        self.stdout.write("Computing summary (roads are the slow part)...")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {summary}")
            cursor.execute(sql, [SIMPLIFY_TOLERANCE])
            cursor.execute(
                f"SELECT COUNT(*), SUM(landmark_count), SUM(address_count), "
                f"ROUND(SUM(road_km)::numeric, 1) FROM {summary}"
            )
            n, landmarks, addresses, km = cursor.fetchone()

        self.stdout.write(self.style.SUCCESS(
            f"{n} barangays | {landmarks} landmarks | {addresses} addresses | "
            f"{km} km of road | {time.time() - started:.1f}s"
        ))
