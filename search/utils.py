from django.db import connection
import re
from django.db.models import Value, CharField, Max
from django.db.models.functions import Replace
from .models import HouseNumber, Landmark, Barangay, Road
from django.contrib.postgres.search import TrigramWordSimilarity
from django.contrib.gis.db.models.aggregates import Union


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

def search_address(hn, street=None, subdivision=None, barangay=None, municipality=None):
        qs = HouseNumber.objects.all()

        if hn:
            qs = filter_by_hn(qs, hn)

        if street or barangay or municipality or subdivision:
            with connection.cursor() as cursor:
                cursor.execute("SET pg_trgm.similarity_threshold = 0.45;")

        street_clean = None
        if street:
            street_clean = strip_suffix(street) or street
            qs = qs.filter(street_name__trigram_similar=street_clean)

        if barangay:
            qs = qs.filter(barangay__trigram_similar=barangay)

        if municipality:
            qs = qs.filter(municipality__trigram_similar=municipality)

        if subdivision:
            qs = qs.filter(subdivision__trigram_similar=subdivision)

        # Numeric street check last, since it turns the queryset into a list
        if street_clean:
            query_numbers = extract_block_numbers(street_clean)
            if query_numbers:
                # Every number in the query must also appear in the candidate's street name
                return [
                    addr for addr in qs
                    if query_numbers.issubset(extract_block_numbers(addr.street_name))
                ][:20]

        return qs[:20]

    
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
            ).filter(sim__gte=THRESHOLD).order_by('-sim').first()
            
            if best_city_row:
                # Now get ALL barangay rows under that exact city name, and union their geometries
                city_admins = Barangay.objects.filter(city=best_city_row.city)
                city_union = city_admins.aggregate(union=Union('geom'))['union']
                if city_union:
                    qs = qs.filter(geom__intersects=city_union)

        # Match barangay independently
        if barangay:
            brgy_pool = city_admins if city_admins is not None else Barangay.objects.all()
            scored = brgy_pool.annotate(
                sim=TrigramWordSimilarity(barangay, 'name')
            ).filter(sim__gte=THRESHOLD)

            best_sim = scored.aggregate(m=Max('sim'))['m']
            if best_sim is not None:
                # all barangays tied for the best score (same name in many cities)
                best_rows = scored.filter(sim=best_sim)
                brgy_union = best_rows.aggregate(union=Union('geom'))['union']
                if brgy_union:
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
        ).filter(brgy_sim__gte=.85, city_sim__gte=.85)
    
    elif barangay and not city :
        qs = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(barangay, "name")
        ).filter(sim__gte=.85)
    
    elif city and not barangay:
        qs = Barangay.objects.annotate(
            sim=TrigramWordSimilarity(city, "city")
        ).filter(sim__gte=.85)
    
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