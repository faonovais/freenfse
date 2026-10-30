"""Criação do primeiro Master em uma instalação nova (não há cadastro público)."""

import pytest
from django.core.management import call_command

from core.models import Usuario

pytestmark = pytest.mark.django_db


def test_createsuperuser_cria_o_master_identificado_pelo_email(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "senha-de-teste-123")

    call_command(
        "createsuperuser", interactive=False, email="Admin@Example.com", nome="Administrador"
    )

    master = Usuario.objects.get(email="admin@example.com")
    assert master.is_master is True
    assert master.is_active is True
    assert master.check_password("senha-de-teste-123")
    assert master.nome == "Administrador"


def test_o_master_criado_sem_senha_nao_consegue_entrar_por_senha():
    call_command("createsuperuser", interactive=False, email="sem-senha@example.com", nome="X")

    assert Usuario.objects.get(email="sem-senha@example.com").has_usable_password() is False
