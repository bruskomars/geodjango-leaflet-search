from django.shortcuts import render

# Create your views here.
def leaflet_map(request):
    return render(request, "maps_frontend/leaflet.html")

def insights(request):
    return render(request, "maps_frontend/insights.html")

def quality(request):
    return render(request, "maps_frontend/quality.html")

def radius(request):
    return render(request, "maps_frontend/radius.html")

def density(request):
    return render(request, "maps_frontend/density.html")

def clusters(request):
    return render(request, "maps_frontend/clusters.html")

def names(request):
    return render(request, "maps_frontend/names.html")