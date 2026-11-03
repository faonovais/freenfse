"""Rotas do app operacao."""

from django.urls import path

from . import views

urlpatterns = [path("saude/", views.saude_da_instalacao, name="saude")]
