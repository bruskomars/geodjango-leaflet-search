from django.urls import path
from . import views

app_name = "maps_frontend"
urlpatterns = [
    path("", views.leaflet_map, name="leaflet_map"),
    path("insights/", views.insights, name="insights"),
    path("quality/", views.quality, name="quality"),
    path("radius/", views.radius, name="radius"),
    path("density/", views.density, name="density"),
    path("clusters/", views.clusters, name="clusters"),
    path("names/", views.names, name="names"),
    path("roads/", views.roads, name="roads"),
    path("consistency/", views.consistency, name="consistency"),
    path("compare/", views.compare, name="compare"),
]