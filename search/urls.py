from django.urls import path
from . import views

urlpatterns = [
    path("search/", views.CrossModelSearchView.as_view(), name="cross-model-search"),
]