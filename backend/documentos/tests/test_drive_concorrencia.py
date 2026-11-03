"""Cópias simultâneas ao Drive: threads reais, conexões reais ao PostgreSQL, Drive simulado.

O Drive aceita pastas com o mesmo nome e a listagem dele atrasa (aqui, 30 s): o que impede a
pasta duplicada é a trava por empresa + o cache `caminho → ID`. Cada proteção tem a sua mutação:
sem a trava ou sem o cache, estes testes reprovam.
"""

import pytest
from django_tenants.utils import schema_context

from documentos.models import ArquivoDrive, PastaDrive
from documentos.services.drive import envio
from documentos.tests.apoio import ativar_drive, nota_avulsa
from documentos.tests.simulados import DriveSimulado
from fiscal.models import Nfse
from fiscal.tests.persistencia.apoio_threads import executar_em_paralelo

pytestmark = pytest.mark.django_db(transaction=True)
PARALELAS = 6


def _enviar(drive):
    trocas = {"cliente": lambda _c: drive}

    def executar(nfse_id):
        return envio.enviar_nota(Nfse.objects.get(pk=nfse_id), trocas=trocas, papeis=("xml",))

    return executar


def test_copias_simultaneas_ao_mesmo_caminho_novo_criam_cada_pasta_uma_so_vez(empresas_confirmadas):
    alfa, _ = empresas_confirmadas
    drive = DriveSimulado(latencia=0.05, atraso_de_indexacao=30)
    with schema_context(alfa.schema_name):
        ativar_drive(modelo_subpastas="{ano}/{mes}", modelo_arquivo="NFSe {numero_nfse} - {chave}")
        ids = [nota_avulsa(n).pk for n in range(1, PARALELAS + 1)]
    executar = _enviar(drive)

    resultados, erros = executar_em_paralelo(
        [(alfa.schema_name, lambda i=i: executar(i)) for i in ids]
    )

    assert erros == [None] * PARALELAS
    assert sorted(p["nome"] for p in drive.pastas()) == ["11", "2026"]  # uma pasta por nível
    assert len(drive.arquivos()) == PARALELAS
    with schema_context(alfa.schema_name):
        assert PastaDrive.objects.count() == 2
        assert set(ArquivoDrive.objects.values_list("situacao", flat=True)) == {"enviado"}
        assert ArquivoDrive.objects.values("pasta_id").distinct().count() == 1


def test_copias_simultaneas_com_o_mesmo_nome_ganham_sufixos_distintos(empresas_confirmadas):
    alfa, _ = empresas_confirmadas
    drive = DriveSimulado(latencia=0.03, atraso_de_indexacao=30)
    with schema_context(alfa.schema_name):
        ativar_drive(
            modelo_subpastas="{ano}", modelo_arquivo="NFSe {numero_nfse} - {cnpj_emitente}"
        )
        ids = [nota_avulsa(7, chave=str(n) * 50).pk for n in range(1, 5)]  # mesmo número e CNPJ
    executar = _enviar(drive)

    _, erros = executar_em_paralelo([(alfa.schema_name, lambda i=i: executar(i)) for i in ids])

    assert erros == [None] * 4
    cnpj = alfa.cnpj
    esperados = {f"NFSe 7 - {cnpj}.xml"} | {f"NFSe 7 - {cnpj} ({n}).xml" for n in (2, 3, 4)}
    assert {a["nome"] for a in drive.arquivos()} == esperados  # nenhum sobrescreveu outro
