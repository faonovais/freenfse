"""Rotas usadas nos testes: as da aplicação mais as do app de apoio."""

from django.urls import include, path

from .urls import urlpatterns as urlpatterns_da_aplicacao

urlpatterns = [
    *urlpatterns_da_aplicacao,
    path("api/teste/", include("apoio_testes.api")),
]
