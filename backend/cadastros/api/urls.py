"""Rotas de cadastros (`/api/cadastros/`): rotas de empresa, exigem `X-Empresa`."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

roteador = SimpleRouter()
roteador.register("pessoas", views.PessoaViewSet, basename="pessoa")
roteador.register("servicos", views.ServicoViewSet, basename="servico")
roteador.register("perfis", views.PerfilPessoaViewSet, basename="perfil-pessoa")

urlpatterns = [
    path("copia/pessoas/", views.CopiaPessoasView.as_view(), name="copia-pessoas"),
    path("municipios/", views.MunicipioView.as_view(), name="municipios"),
    *roteador.urls,
]
