"""Rotas fiscais (`/api/fiscal/`): rotas de empresa, exigem `X-Empresa`."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import notas, views

roteador = SimpleRouter()
roteador.register("notas", notas.NotaViewSet, basename="nota")

urlpatterns = [
    path("identidade/", views.IdentidadeView.as_view(), name="fiscal-identidade"),
    path("parametros/", views.ParametrosView.as_view(), name="fiscal-parametros"),
    path(
        "parametros/verificar-convenio/",
        views.VerificarConvenioView.as_view(),
        name="fiscal-verificar-convenio",
    ),
    path("certificado/", views.CertificadoView.as_view(), name="fiscal-certificado"),
    path("logo/<str:tema>/", views.LogoView.as_view(), name="fiscal-logo"),
    *roteador.urls,
]
