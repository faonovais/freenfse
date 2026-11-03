"""Rotas dos agendamentos (`/api/agendamentos/`): rotas de empresa, exigem `X-Empresa`."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

roteador = SimpleRouter()
roteador.register("modelos", views.ModeloViewSet, basename="modelo-nfse")
roteador.register("agendamentos", views.AgendamentoViewSet, basename="agendamento")
roteador.register("execucoes", views.ExecucaoViewSet, basename="execucao-agendamento")
roteador.register("rascunhos", views.RascunhoViewSet, basename="rascunho")

urlpatterns = [
    path("opcoes/", views.OpcoesView.as_view(), name="agendamentos-opcoes"),
    *roteador.urls,
]
