"""Fixtures dos testes de documentos: empresa pronta, Sefin simulada e fila falsa."""

import pytest
from django_tenants.utils import schema_context

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
        self.chamadas = []

    def nomes(self):
        return [nome for nome, _args in self.chamadas]


@pytest.fixture(autouse=True)
def fila(monkeypatch):
    """Troca o `delay` de todas as tarefas de documentos por um registro em memória."""
    from documentos import tasks

    registro = FilaFalsa()
    for nome in (
        "processar_envio_email",
        "enviar_nota_ao_drive",
        "enviar_evento_ao_drive",
        "gerar_exportacao",
    ):
        monkeypatch.setattr(
            getattr(tasks, nome), "delay", lambda *a, _n=nome: registro.chamadas.append((_n, a))
        )
    return registro


@pytest.fixture(autouse=True)
def on_commit_imediato(monkeypatch):
    """O teste roda numa transação que nunca confirma: o `on_commit` das views roda na hora."""
    from types import SimpleNamespace

    from documentos.api import views

    monkeypatch.setattr(views, "transaction", SimpleNamespace(on_commit=lambda f: f()))


@pytest.fixture(autouse=True)
def pasta_de_exportacoes(settings, tmp_path):
    """Os ZIPs do download em lote vão para uma pasta temporária do teste."""
    settings.FREENFSE_EXPORTACOES_DIR = str(tmp_path / "exportacoes")
    return tmp_path / "exportacoes"


@pytest.fixture
def empresa_ativa(empresa_a):
    """Executa o teste no schema da empresa A (como a requisição faria)."""
    with schema_context(empresa_a.schema_name):
        yield empresa_a


class Provedores:
    """Os três provedores de e-mail simulados que a fábrica passa a usar."""

    def __init__(self):
        """Cria um servidor SMTP, um serviço Gmail e uma sessão Graph falsos."""
        from documentos.tests.simulados import (
            ServicoGmailFalso,
            ServidorSmtpFalso,
            SessaoGraphFalsa,
        )

        self.smtp = ServidorSmtpFalso()
        self.gmail = ServicoGmailFalso()
        self.graph = SessaoGraphFalsa()


@pytest.fixture
def provedores(monkeypatch):
    """Faz `criar_provedor` usar os provedores simulados (nada vai à rede)."""
    from documentos.services.email import fabrica

    simulados = Provedores()
    monkeypatch.setattr(
        fabrica,
        "pontos_de_troca",
        lambda: {
            "smtp": simulados.smtp,
            "gmail": lambda _conta, _remetente: simulados.gmail,
            "graph": simulados.graph,
        },
    )
    return simulados


@pytest.fixture
def drive_simulado(monkeypatch):
    """Faz o código usar um Drive simulado no lugar do Google."""
    from documentos.services.drive import envio
    from documentos.tests.simulados import DriveSimulado

    drive = DriveSimulado()
    monkeypatch.setattr(envio, "pontos_de_troca", lambda: {"cliente": lambda _c: drive})
    return drive
