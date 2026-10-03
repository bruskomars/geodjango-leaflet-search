from django.contrib.gis.db import models


class HouseNumber(models.Model):
    src_id = models.BigIntegerField(null=True, db_index=True)
    municipality = models.CharField(max_length=100, null=True, blank=True)
    barangay = models.CharField(max_length=100, null=True, blank=True)
    subdivision = models.CharField(max_length=200, null=True, blank=True)
    house_number = models.CharField(max_length=50, null=True, blank=True)
    street_name = models.CharField(max_length=200, null=True, blank=True)
    geom = models.PointField(srid=4326)


class Barangay(models.Model):
    src_id = models.BigIntegerField(null=True, db_index=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    geom = models.MultiPolygonField(srid=4326)


class Road(models.Model):
    src_id = models.BigIntegerField(null=True, db_index=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    prefix_type = models.CharField(max_length=50, null=True, blank=True)
    suffix_type = models.CharField(max_length=50, null=True, blank=True)
    geom = models.MultiLineStringField(srid=4326)


class Landmark(models.Model):
    src_id = models.BigIntegerField(null=True, db_index=True)
    name = models.CharField(max_length=300, null=True, blank=True)
    geom = models.PointField(srid=4326)