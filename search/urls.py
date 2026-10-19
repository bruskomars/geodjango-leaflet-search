from django.urls import path
from . import views
from .analysis import BarangaySummaryView
from .quality import DataQualityView, AreasView

urlpatterns = [
    path("search/", views.CrossModelSearchView.as_view(), name="cross-model-search"),
    path("analysis/barangays/", BarangaySummaryView.as_view(), name="barangay-summary"),
    path("analysis/quality/", DataQualityView.as_view(), name="data-quality"),
    path("analysis/areas/", AreasView.as_view(), name="analysis-areas"),
]