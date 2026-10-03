import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from search.models import Barangay, HouseNumber, Landmark, Road

BATCH = 2000


def to_int(v):
    return int(v) if v is not None else None


LAYERS = {
    "barangays": (
        "ncr_admin.geojson", Barangay,
        lambda p: dict(src_id=to_int(p.get("id")), region=p.get("name1"),
                       city=p.get("name2"), name=p.get("name3")),
    ),
    "housenumbers": (
        "ncr_hn.geojson", HouseNumber,
        lambda p: dict(src_id=to_int(p.get("id")), municipality=p.get("municipali"),
                       barangay=p.get("barangay"), subdivision=p.get("subdivisio"),
                       house_number=p.get("hn"), street_name=p.get("sn")),
    ),
    "roads": (
        "ncr_roads.geojson", Road,
        lambda p: dict(src_id=to_int(p.get("id")), name=p.get("name"),
                       prefix_type=p.get("name_pf"), suffix_type=p.get("name_sf")),
    ),
    "landmarks": (
        "ncr_landmark.geojson", Landmark,
        lambda p: dict(src_id=to_int(p.get("id")), name=p.get("name")),
    ),
}


class Command(BaseCommand):
    help = "Load GeoJSON layers from data/ into PostGIS (reloads each layer from scratch)."

    def add_arguments(self, parser):
        parser.add_argument("layers", nargs="*",
                            help="Any of: " + ", ".join(LAYERS) + " (default: all)")

    def handle(self, *args, **options):
        names = options["layers"] or list(LAYERS)
        for name in names:
            if name not in LAYERS:
                raise CommandError(f"Unknown layer '{name}'. Choose from: {', '.join(LAYERS)}")

        for name in names:
            filename, model, mapper = LAYERS[name]
            path = Path(settings.BASE_DIR) / "data" / filename
            self.stdout.write(f"Loading {name} from {path.name} ...")
            with open(path, encoding="utf-8") as f:
                features = json.load(f)["features"]

            total = skipped = 0
            batch = []
            with transaction.atomic():
                model.objects.all().delete()
                for feat in features:
                    geom = feat.get("geometry")
                    if not geom:
                        skipped += 1
                        continue
                    batch.append(model(
                        geom=GEOSGeometry(json.dumps(geom), srid=4326),
                        **mapper(feat.get("properties") or {}),
                    ))
                    if len(batch) >= BATCH:
                        model.objects.bulk_create(batch)
                        total += len(batch)
                        batch = []
                if batch:
                    model.objects.bulk_create(batch)
                    total += len(batch)

            self.stdout.write(self.style.SUCCESS(f"  {name}: {total} loaded, {skipped} skipped"))