from .models import Barangay, Landmark, Road, HouseNumber

from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework import serializers
from django.db import connection

class AdminSerializer(GeoFeatureModelSerializer):
    id = serializers.IntegerField(source="src_id", read_only=True)
    province = serializers.CharField(source="region", read_only=True)
    barangay = serializers.CharField(source="name", read_only=True)

    class Meta:
        model = Barangay
        geo_field = "geom"
        fields = ["id", "province", "city", "barangay"]


class LandmarkSerializer(GeoFeatureModelSerializer):
    id = serializers.IntegerField(source="src_id", read_only=True)

    class Meta:
        model = Landmark
        geo_field = "geom"
        fields = ["id", "name"]


class RoadSerializer(GeoFeatureModelSerializer):
    id = serializers.IntegerField(source="src_id", read_only=True)
    name_pf = serializers.CharField(source="prefix_type", read_only=True)
    name_sf = serializers.CharField(source="suffix_type", read_only=True)
    admin = serializers.SerializerMethodField()

    class Meta:
        model = Road
        geo_field = "geom"
        fields = ["id", "name", "name_pf", "name_sf", "admin"]
        
    def get_admin(self, obj):
            admin = Barangay.objects.filter(geom__intersects=obj.geom).first()
            
            if not admin:
                return {"city": None, "barangay": None, "province": None}
            
            return {
                "city" : admin.city, 
                "barangay" : admin.name, 
                "province" : admin.region
            }


class AddressSerializer(GeoFeatureModelSerializer):
    id = serializers.IntegerField(source="src_id", read_only=True)
    hn = serializers.CharField(source="house_number", read_only=True)
    sn = serializers.CharField(source="street_name", read_only=True)
    street_base_name = serializers.CharField(source="street_name", read_only=True)

    class Meta:
        model = HouseNumber
        geo_field = "geom"
        fields = ["id", "municipality", "barangay", "subdivision",
                  "hn", "sn", "street_base_name"]

class LandmarkGeoSerializer(GeoFeatureModelSerializer):
    admin = serializers.SerializerMethodField()
    nearest_streets = serializers.SerializerMethodField()
    id = serializers.IntegerField(source="src_id", read_only=True)
    
    class Meta:
        model = Landmark
        geo_field = "geom"
        fields = ["id", "name", "admin", "nearest_streets"]
        
    def get_admin(self, obj):
        admin = Barangay.objects.filter(geom__intersects=obj.geom).first()
        
        if not admin:
            return {"city": None, "barangay": None, "province": None}
        
        return {
            "city" : admin.city, 
            "barangay" : admin.name, 
            "province" : admin.region
        }

    
    def get_nearest_streets(self, obj):
        table = Road._meta.db_table  # "search_road", from the model, not user input
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT name, ST_DistanceSphere(geom, ST_GeomFromEWKB(%s)) as distance
                FROM {table}
                WHERE name IS NOT NULL AND name != ''
                ORDER BY geom <-> ST_GeomFromEWKB(%s)
                LIMIT 20
            """, [bytes(obj.geom.ewkb), bytes(obj.geom.ewkb)])
            rows = cursor.fetchall()

        seen = set()
        result = []
        for name, distance in rows:
            if name in seen:
                continue
            seen.add(name)
            result.append({"name": name, "distance_m": distance})
            if len(result) == 5:
                break

        return result

