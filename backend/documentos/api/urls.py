"""Rotas de documentos (`/api/documentos/`): rotas de empresa, exigem `X-Empresa`."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

roteador = SimpleRouter()
roteador.register("exportacoes", views.ExportacaoViewSet, basename="exportacao")

urlpatterns = [
    path("config/email/", views.ConfigEmailView.as_view(), name="documentos-config-email"),
    path("config/email/teste/", views.TesteEmailView.as_view(), name="documentos-teste-email"),
    path("config/drive/", views.ConfigDriveView.as_view(), name="documentos-config-drive"),
    path("config/drive/previa/", views.PreviaDriveView.as_view(), name="documentos-previa-drive"),
    path("notas/<int:pk>/envios/", views.EnviosDaNotaView.as_view(), name="documentos-envios"),
    path("notas/<int:pk>/email/", views.EmailDaNotaView.as_view(), name="documentos-email-nota"),
    path(
        "notas/<int:pk>/drive/reenviar/",
        views.ReenviarDriveNotaView.as_view(),
        name="documentos-drive-nota",
    ),
    path(
        "envios-email/<int:pk>/reenviar/",
        views.ReenviarEmailView.as_view(),
        name="documentos-reenviar-email",
    ),
    path(
        "drive/reenviar-periodo/",
        views.ReenviarDrivePeriodoView.as_view(),
        name="documentos-drive-periodo",
    ),
    path(
        "exportacoes/<int:pk>/download/",
        views.ExportacaoViewSet.as_view({"get": "download"}),
        name="exportacao-download",
    ),
    *roteador.urls,
]
