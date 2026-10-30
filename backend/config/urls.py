"""Rotas do projeto."""

from django.urls import include, path

urlpatterns = [
    path("api/", include("core.api.urls")),
]
