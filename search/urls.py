from django.urls import path
from . import views
from .analysis import BarangaySummaryView

urlpatterns = [
    path("search/", views.CrossModelSearchView.as_view(), name="cross-model-search"),
    path("analysis/barangays/", BarangaySummaryView.as_view(), name="barangay-summary"),
]