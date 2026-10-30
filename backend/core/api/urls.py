"""Rotas da API do app core."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

# Administração global (só Master): sem exclusão; desative em vez de apagar.
roteador = SimpleRouter()
roteador.register("empresas", views.EmpresaViewSet, basename="admin-empresa")
roteador.register("usuarios", views.UsuarioViewSet, basename="admin-usuario")
roteador.register("vinculos", views.VinculoViewSet, basename="admin-vinculo")

urlpatterns = [
    path("versao/", views.versao, name="versao"),
    path("eu/", views.EuView.as_view(), name="eu"),
    path("empresa-ativa/", views.EmpresaAtivaView.as_view(), name="empresa-ativa"),
    path("admin-global/permissoes/", views.PermissoesView.as_view(), name="admin-permissoes"),
    path("admin-global/", include(roteador.urls)),
]
