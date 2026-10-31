"""Fixtures dos testes de agendamentos: empresa pronta, Sefin simulada e fila falsa."""

import pytest

from fiscal.tests.conftest import (  # noqa: F401 - fixtures reutilizadas dos testes fiscais
    api_de,
    api_do_master,
    empresa_pronta,
    empresas_confirmadas,
    nova_nota,
    relogio_fiscal,
    sefin,
)


class FilaFalsa:
    """Registra o que seria enfileirado no Celery (nada vai ao broker)."""

    def __init__(self):
        """Começa vazia."""
        self.emissoes = []


@pytest.fixture(autouse=True)
def fila(monkeypatch):
    """Troca o `delay` da emissão por um registro em memória (a emissão roda na mão)."""
    from fiscal import tasks

    registro = FilaFalsa()
    monkeypatch.setattr(
        tasks.emitir_nfse,
        "delay",
        lambda schema, nfse_id: registro.emissoes.append((schema, nfse_id)),
    )
    return registro


@pytest.fixture(autouse=True)
def on_commit_imediato(monkeypatch):
    """O teste roda numa transação que nunca confirma: o `on_commit` das views roda na hora."""
    from types import SimpleNamespace

    from agendamentos.api import views

    monkeypatch.setattr(views, "transaction", SimpleNamespace(on_commit=lambda f: f()))
