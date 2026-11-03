"""Rotas do projeto."""

from django.urls import include, path

urlpatterns = [
    path("api/cadastros/", include("cadastros.api.urls")),
    path("api/fiscal/", include("fiscal.api.urls")),
    path("api/documentos/", include("documentos.api.urls")),
    path("api/", include("core.api.urls")),
    # Autenticação (django-allauth, modo headless): API JSON para a SPA.
    path("_allauth/", include("allauth.headless.urls")),
    # Retorno (callback) dos provedores de login social; as telas de conta do
    # allauth ficam desligadas (HEADLESS_ONLY).
    path("accounts/", include("allauth.urls")),
]
