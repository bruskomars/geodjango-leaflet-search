from django.shortcuts import render

# Create your views here.
def leaflet_map(request):
    return render(request, "maps_frontend/leaflet.html")
