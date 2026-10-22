from django.urls import path

from search.consistency import ConsistencyView
from search.names import NamePointsView, NameSummaryView
from search.roadstats import RoadGeometryView
from . import views
from .analysis import BarangaySummaryView
from .quality import DataQualityView, AreasView
from .radius import RadiusAnalysisView
from .hexgrid import HexGridView
from .clusters import ClustersView
from .names import NameSummaryView, NamePointsView
from .roadstats import RoadSummaryView, RoadGeometryView
from .consistency import ConsistencyView

urlpatterns = [
    path("search/", views.CrossModelSearchView.as_view(), name="cross-model-search"),
    path("analysis/barangays/", BarangaySummaryView.as_view(), name="barangay-summary"),
    path("analysis/quality/", DataQualityView.as_view(), name="data-quality"),
    path("analysis/areas/", AreasView.as_view(), name="analysis-areas"),
    path("analysis/radius/", RadiusAnalysisView.as_view(), name="radius-analysis"),
    path("analysis/hexgrid/", HexGridView.as_view(), name="hexgrid"),
    path("analysis/clusters/", ClustersView.as_view(), name="clusters"),
    path("analysis/names/", NameSummaryView.as_view(), name="name-summary"),
    path("analysis/names/points/", NamePointsView.as_view(), name="name-points"),
    path("analysis/roads/", RoadSummaryView.as_view(), name="road-summary"),
    path("analysis/roads/geometry/", RoadGeometryView.as_view(), name="road-geometry"),
    path("analysis/consistency/", ConsistencyView.as_view(), name="consistency"),
]