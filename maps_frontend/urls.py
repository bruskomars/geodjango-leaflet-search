from django.urls import path
from . import views

app_name = "maps_frontend"
urlpatterns = [
    path("", views.leaflet_map, name="leaflet_map"),
    path("insights/", views.insights, name="insights"),
    path("quality/", views.quality, name="quality"),
]