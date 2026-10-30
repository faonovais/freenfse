import base64

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import NotSupportedError, connection
from django_tenants.utils import schema_context

from apoio_testes.models import Anotacao
from core import crypto

CHAVE_1 = base64.urlsafe_b64encode(bytes(range(32))).decode()
CHAVE_2 = base64.urlsafe_b64encode(bytes(range(32, 64))).decode()
PFX_FICTICIO = b"\x30\x82fake-pfx\x00\xff" * 20
VALOR_CIFRADO = "valor-ficticio-123"


def _bruto(campo, pk):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {campo} FROM apoio_testes_anotacao WHERE id = %s", [pk])  # noqa: S608
        valor = cursor.fetchone()[0]
    return bytes(valor) if isinstance(valor, memoryview) else valor


def test_campos_guardam_cifrado_e_o_modelo_ve_o_claro(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        nota = Anotacao.objects.create(texto="x", segredo=VALOR_CIFRADO, arquivo=PFX_FICTICIO)

        assert Anotacao.objects.get(pk=nota.pk).segredo == VALOR_CIFRADO
        assert Anotacao.objects.get(pk=nota.pk).arquivo == PFX_FICTICIO
        assert _bruto("segredo", nota.pk).startswith("v1:")
        assert VALOR_CIFRADO not in _bruto("segredo", nota.pk)
        assert _bruto("arquivo", nota.pk).startswith(b"v1:")
        assert PFX_FICTICIO not in _bruto("arquivo", nota.pk)


def test_campos_aceitam_nulo(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        nota = Anotacao.objects.create(texto="vazio")

        recarregada = Anotacao.objects.get(pk=nota.pk)
        assert recarregada.segredo is None
        assert recarregada.arquivo is None
        assert Anotacao.objects.filter(segredo__isnull=True).count() == 1


def test_filtro_por_valor_cifrado_nao_e_permitido(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name), pytest.raises(NotSupportedError):
        list(Anotacao.objects.filter(segredo="qualquer"))


def test_rotacao_de_chave_recriptografa_em_todas_as_empresas(settings, empresa_a, empresa_b):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    ids = {}
    for empresa, segredo in (
        (empresa_a, "segredo-da-empresa-a"),
        (empresa_b, "segredo-da-empresa-b"),
    ):
        with schema_context(empresa.schema_name):
            nota = Anotacao.objects.create(texto="n", segredo=segredo, arquivo=PFX_FICTICIO)
            ids[empresa.schema_name] = nota.pk
            assert _bruto("segredo", nota.pk).startswith("v1:")

    # Rotação: chave nova na frente, a antiga mantida só para decifrar.
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}", f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        assert Anotacao.objects.get(pk=ids[empresa_a.schema_name]).segredo == "segredo-da-empresa-a"

    call_command("recriptografar", stdout=_SaidaDescartavel())

    for empresa, segredo in (
        (empresa_a, "segredo-da-empresa-a"),
        (empresa_b, "segredo-da-empresa-b"),
    ):
        with schema_context(empresa.schema_name):
            pk = ids[empresa.schema_name]
            assert _bruto("segredo", pk).startswith("v2:")
            assert _bruto("arquivo", pk).startswith(b"v2:")
            assert Anotacao.objects.get(pk=pk).segredo == segredo
            assert Anotacao.objects.get(pk=pk).arquivo == PFX_FICTICIO

    # Com tudo recriptografado, a chave antiga pode sair da configuração.
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}"]
    with schema_context(empresa_b.schema_name):
        assert Anotacao.objects.get(pk=ids[empresa_b.schema_name]).segredo == "segredo-da-empresa-b"


def test_recriptografar_dry_run_nao_grava(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        nota = Anotacao.objects.create(texto="n", segredo="segredo")
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}", f"1:{CHAVE_1}"]

    saida = _SaidaDescartavel()
    call_command("recriptografar", "--dry-run", stdout=saida)

    with schema_context(empresa_a.schema_name):
        assert _bruto("segredo", nota.pk).startswith("v1:")
    assert "a recriptografar" in saida.texto


def test_recriptografar_e_idempotente(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        Anotacao.objects.create(texto="n", segredo="segredo")
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}", f"1:{CHAVE_1}"]
    call_command("recriptografar", stdout=_SaidaDescartavel())

    saida = _SaidaDescartavel()
    call_command("recriptografar", stdout=saida)

    assert "recriptografados para a chave v2: 0" in saida.texto


def test_recriptografar_sem_a_chave_antiga_falha_sem_vazar_o_valor(settings, empresa_a):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    with schema_context(empresa_a.schema_name):
        Anotacao.objects.create(texto="n", segredo="segredo-que-nao-pode-vazar")
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}"]  # a chave v1 sumiu antes da hora

    with pytest.raises(CommandError) as erro:
        call_command("recriptografar", stdout=_SaidaDescartavel())

    assert "v1" in str(erro.value)
    assert "segredo-que-nao-pode-vazar" not in str(erro.value)


def test_recriptografar_sem_chaves_configuradas_falha(settings):
    settings.FREENFSE_CHAVES = []

    with pytest.raises(CommandError):
        call_command("recriptografar", stdout=_SaidaDescartavel())


def test_gerar_chave_imprime_uma_chave_valida(settings):
    saida = _SaidaDescartavel()
    call_command("gerar_chave", stdout=saida)
    settings.FREENFSE_CHAVES = [f"1:{saida.texto.strip()}"]

    assert crypto.decifrar_texto(crypto.cifrar_texto("ok")) == "ok"


class _SaidaDescartavel:
    """Captura a saída do comando sem imprimir nos logs dos testes."""

    def __init__(self):
        self.texto = ""

    def write(self, texto):
        self.texto += texto

    def flush(self):
        pass
