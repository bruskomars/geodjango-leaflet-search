from django.db import connection
import re
from django.db.models import Value, CharField, Max, Exists, OuterRef
from django.db.models.functions import Replace, Greatest
from .models import HouseNumber, Landmark, Barangay, Road
from django.contrib.postgres.search import TrigramWordSimilarity, TrigramSimilarity
from django.contrib.gis.db.models.aggregates import Union

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D


def find_nearby_matching_street(geom, street_query, name_threshold=0.35, k=20, max_distance_m=150):
        """
        Check whether a street matching `street_query` exists within `max_distance_m`
        of this landmark, regardless of its rank among nearby streets.
        Uses the fast index-accelerated KNN operator to fetch candidates,
        then filters by distance + name similarity in Python.
        """
        table = Road._meta.db_table  # "search_road", from the model, not user input
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT name, similarity(name, %s) as sim, ST_DistanceSphere(geom, %s) as distance
                FROM {table}
                WHERE name IS NOT NULL AND name != ''
                ORDER BY geom <-> %s
                LIMIT %s
            """, [street_query, bytes(geom.ewkb), bytes(geom.ewkb), k])
            rows = cursor.fetchall()

        return any(
            distance <= max_distance_m and sim >= name_threshold
            for name, sim, distance in rows
        )

def filter_by_hn(queryset, hn):
    """
    Filter a queryset by house number (exact match, allowing a letter suffix
    but rejecting numeric continuations — e.g. "145" matches "145A" but not "1450").
    Extracted from AddressListView's original inline logic.
    """
    def normalize_hn(value):
        return value.replace(' ', '').replace('-', '')

    hn_normalized = normalize_hn(hn)
    escaped = re.escape(hn_normalized)
    pattern = rf'^{escaped}$|^{escaped}[^0-9]'

    return queryset.annotate(
        hn_normalized=Replace(
            Replace('house_number', Value(' '), Value(''), output_field=CharField()),
            Value('-'), Value(''), output_field=CharField()
        )
    ).filter(hn_normalized__iregex=pattern)


STREET_SUFFIXES = r'\b(street|st\.?|avenue|ave\.?|avenida|road|rd\.?|boulevard|blvd\.?|drive|dr\.?|lane|ln\.?|calle)\b'


def strip_suffix(value):
    cleaned = re.sub(STREET_SUFFIXES, '', value, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def extract_block_numbers(value):
    return set(re.findall(r'\d+', value))

ADMIN_NOISE = re.compile(r'\b(city of|city|municipality of|municipality)\b', re.I)

def clean_admin(text):
    return ADMIN_NOISE.sub('', text).strip() or text

def search_address(hn, street=None, subdivision=None, barangay=None, municipality=None):
        qs = HouseNumber.objects.all()

        if hn:
            qs = filter_by_hn(qs, hn)

        street_clean = None
        if street:
            street_clean = strip_suffix(street) or street
            qs = qs.annotate(
                street_sim=Greatest(
                    TrigramSimilarity('street_name', street_clean),
                    TrigramWordSimilarity(street_clean, 'street_name'),
                )
            ).filter(street_sim__gte=0.6)

        if municipality:
            qs = qs.annotate(
                muni_sim=TrigramWordSimilarity(clean_admin(municipality), 'municipality')
            ).filter(muni_sim__gte=0.6)

        if barangay:
            qs = qs.annotate(
                brgy_sim=TrigramWordSimilarity(clean_admin(barangay), 'barangay')
            ).filter(brgy_sim__gte=0.6)

        if subdivision:
            qs = qs.annotate(
                sub_sim=TrigramWordSimilarity(subdivision, 'subdivision')
            ).filter(sub_sim__gte=0.5)

        if street_clean:
            qs = qs.order_by('-street_sim')      # so the top 20 are the best, not arbitrary
            query_numbers = extract_block_numbers(street_clean)
            if query_numbers:
                return [
                    addr for addr in qs[:500]    # cap, don't iterate the whole table
                    if query_numbers.issubset(extract_block_numbers(addr.street_name))
                ][:20]

        return qs

    
def search_landmark(landmark_query, barangay=None, city=None, street=None):
        THRESHOLD = .35
        # search landmark table and annotates the query and landmark name
        qs = Landmark.objects.annotate(
            sim=TrigramWordSimilarity(landmark_query, "name")).filter(sim__gte=.65)
        
        # self.admin_check_spatial(city, barangay, THRESHOLD, qs)
        city_admins = None
        
        if city:
            best_city_row = Barangay.objects.annotate(
                sim=TrigramWordSimilarity(city, 'city')
            ).filter(sim__gte=.65).order_by('-sim').first()
            
            if not best_city_row:
                return []
            

            city_admins = Barangay.objects.filter(city=best_city_row.city)
            qs = qs.filter(geom__intersects=city_admins.aggregate(u=Union('geom'))['u'])

        # Match barangay independently
        if barangay:
            pool = city_admins if city_admins is not None else Barangay.objects.all()
            scored = pool.annotate(
                sim=Greatest(
                    TrigramSimilarity('name', barangay),       # symmetric, stricter
                    TrigramWordSimilarity(barangay, 'name'),
                )
            ).filter(sim__gte=.4)                              # lower: typos score lower

            best_sim = scored.aggregate(m=Max('sim'))['m']
            if best_sim is None:
                return []                      # typed a barangay but none matched
            # keep only near-best, not just exact ties
            best_rows = scored.filter(sim__gte=best_sim - 0.05)
            brgy_union = best_rows.aggregate(u=Union('geom'))['u']
            qs = qs.filter(geom__intersects=brgy_union)
                

        # Match street independently (unchanged from before)
        candidates = list(qs.order_by('-sim')[:20])

        if street and candidates:
            candidates = [
                lm for lm in candidates
                if find_nearby_matching_street(lm.geom, street)
            ]

        return candidates

            
def search_admin(barangay=None, city=None):
    if barangay and city:
        qs = Barangay.objects.annotate(
            brgy_sim=TrigramWordSimilarity(barangay, "name"),
            city_sim=TrigramWordSimilarity(city, "city")
        ).filter(brgy_sim__gte=.65, city_sim__gte=.65)
    
    elif barangay and not city :
        qs = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(barangay, "name")
        ).filter(sim__gte=.65)
    
    elif city and not barangay:
        qs = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(city, "city")
        ).filter(sim__gte=.65)
    
    return qs

def search_road(road_query, barangay=None, city=None):
    THRESHOLD = .35
    # search landmark table and annotates the query and landmark name
    qs = Road.objects.annotate(
        sim=TrigramWordSimilarity(road_query, "name")).filter(sim__gte=.65)
    
    # self.admin_check_spatial(city, barangay, THRESHOLD, qs)
    
    if city:
        best_city_row = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(city, 'city')
        ).filter(sim__gte=THRESHOLD).order_by('-sim').first()
        
        if best_city_row:
            # Now get ALL barangay rows under that exact city name, and union their geometries
            city_admins = Barangay.objects.filter(city=best_city_row.city)
            city_union = city_admins.aggregate(union=Union('geom'))['union']
            if city_union:
                qs = qs.filter(geom__intersects=city_union)

    # Match barangay independently
    if barangay:
        brgy_match = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(barangay, 'name')
        ).filter(sim__gte=THRESHOLD).order_by('-sim').first()
        if brgy_match:
            qs = qs.filter(geom__intersects=brgy_match.geom)
    

    # Match street independently (unchanged from before)
    candidates = list(qs.order_by('-sim')[:20])

    return candidates

NEARBY_DEG = 0.003   # ~330 m in degrees, only a cheap index-friendly prefilter

def landmarks_near_point(point, landmark_query, radius_m=200):
    return (
        Landmark.objects
        .annotate(
            sim=TrigramWordSimilarity(landmark_query, 'name'),
            dist=Distance('geom', point),            # meters for 4326 geometry
        )
        .filter(sim__gte=.65)
        .filter(geom__dwithin=(point, NEARBY_DEG))   # uses the spatial index
        .filter(dist__lte=D(m=radius_m))             # exact cut at 200 m
        .order_by('-sim', 'dist')[:10]
    )


from django.db.models import Exists, OuterRef
from django.contrib.gis.db.models.functions import Distance

def search_combined(landmark_query=None, hn=None, street=None, subdivision=None,
                    barangay=None, municipality=None, radius_m=200):
    has_address = any([hn, street, subdivision, barangay, municipality])

    if landmark_query and not has_address:
        return search_landmark(landmark_query, barangay, municipality, street)
    if not has_address:
        return search_address(hn, street, subdivision, barangay, municipality)
    if not landmark_query:
        return search_address(hn, street, subdivision, barangay, municipality)

    addr_qs = search_address(hn, street, subdivision, barangay, municipality)
    addr_qs = addr_qs.filter(geom__isnull=False)

    candidates = (
        Landmark.objects
        .annotate(sim=TrigramWordSimilarity(landmark_query, 'name'))
        .filter(sim__gte=.65)
        .order_by('-sim')[:100]
    )

    results = []
    for lm in candidates:
        nearest = (
            addr_qs
            .filter(geom__dwithin=(lm.geom, 0.003))          # cheap prefilter (~330 m)
            .annotate(dist=Distance('geom', lm.geom))
            .filter(dist__lte=D(m=radius_m))                  # exact 200 m cut
            .order_by('dist')
            .first()
        )
        if nearest:
            lm.dist = nearest.dist
            lm.nearest_address = nearest
            results.append(lm)

    return results[:20]