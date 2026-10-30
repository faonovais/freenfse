"""Rotas da API do app core."""

from django.urls import path

from . import views

urlpatterns = [
    path("versao/", views.versao, name="versao"),
]
