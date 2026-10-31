"""Modelos de caminho do Drive: validação, unicidade, normalização e pré-visualização."""

import pytest

from documentos.models import ConfiguracaoDrive
from documentos.services.drive import caminhos
from documentos.tests.apoio import nota_avulsa


def test_modelo_valido_nao_tem_erros():
    assert (
        caminhos.validar(
            "{ano}/{mes}/{cnpj_emitente} - {nome_emitente}", "NFSe {numero_nfse} - {chave}"
        )
        == {}
    )


@pytest.mark.parametrize(
    ("subpastas", "arquivo", "campo", "trecho"),
    [
        ("{ano}/{inexistente}", "{chave}", "modelo_subpastas", "{inexistente} não existe"),
        ("{ano}/{mes", "{chave}", "modelo_subpastas", "sem o '}'"),
        ("{ano}/mes}", "{chave}", "modelo_subpastas", "sem o '{'"),
        ("{ano}//{mes}", "{chave}", "modelo_subpastas", "nível de pasta vazio"),
        ("/{ano}", "{chave}", "modelo_subpastas", "nível de pasta vazio"),
        ("{ano}\\{mes}", "{chave}", "modelo_subpastas", "Use '/'"),
        ("{ano}", "{dia}/{chave}", "modelo_arquivo", "não pode ter"),
        ("{ano}", "{chave", "modelo_arquivo", "sem o '}'"),
    ],
)
def test_cada_erro_de_modelo_e_apontado(subpastas, arquivo, campo, trecho):
    erros = caminhos.validar(subpastas, arquivo)

    assert trecho in " ".join(erros[campo])


def test_todos_os_erros_vem_de_uma_vez():
    erros = caminhos.validar("{ano}//{x}", "{y")

    assert set(erros) == {"modelo_subpastas", "modelo_arquivo"}
    assert len(erros["modelo_subpastas"]) == 2  # nível vazio e variável desconhecida


@pytest.mark.parametrize(
    ("subpastas", "arquivo", "valido"),
    [
        ("{ano}", "{chave}", True),
        ("{chave}", "arquivo", True),
        ("{ano}", "{numero_nfse} {cnpj_emitente}", True),
        ("{numero_nfse}/{cnpj_emitente}", "nota", True),
        ("{ano}", "{numero_nfse}", False),  # o número só é único por emitente
        ("{ano}", "{cnpj_emitente}", False),
        ("{ano}/{mes}", "NFSe {dia}", False),
        ("", "", True),  # arquivo vazio vale {chave}
    ],
)
def test_regra_de_unicidade_chave_ou_numero_com_cnpj(subpastas, arquivo, valido):
    erros = caminhos.validar(subpastas, arquivo)

    assert (erros == {}) is valido
    if not valido:
        assert "identificar uma única nota" in erros["unicidade"][0]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("A/B\\C", "ABC"),
        ("a\x00b\x1fc\x7f", "abc"),
        ("  muitos    espaços   ", "muitos espaços"),
        ("x" * 250, "x" * 100),
        ("../../etc", "....etc"),
    ],
)
def test_normalizacao_dos_valores(entrada, esperado):
    assert caminhos.normalizar(entrada) == esperado


@pytest.mark.django_db
def test_caminho_da_nota_usa_a_data_de_emissao_em_brasilia_e_normaliza(empresa_ativa):
    import datetime as dt

    # 01/12 02:30 UTC ainda é 30/11 em Brasília: vale a data de emissão local.
    nota = nota_avulsa(7, emitida_em=dt.datetime(2026, 12, 1, 2, 30, tzinfo=dt.UTC))
    empresa_ativa.razao_social = "EMPRESA / TESTE \\ LTDA"
    configuracao = ConfiguracaoDrive(
        modelo_subpastas="{ano}/{mes}/{dia}/{cnpj_emitente} - {nome_emitente}",
        modelo_arquivo="NFSe {numero_nfse} - {dia}{mes}{ano}",
    )

    niveis, nome = caminhos.caminho_da_nota(configuracao, nota, empresa_ativa)

    assert niveis == ["2026", "11", "30", "11222333000181 - EMPRESA TESTE LTDA"]
    assert nome == "NFSe 7 - 30112026"


@pytest.mark.django_db
def test_modelo_de_arquivo_vazio_usa_a_chave_e_subpastas_vazias_vao_para_a_raiz(empresa_ativa):
    nota = nota_avulsa(1)
    configuracao = ConfiguracaoDrive(modelo_subpastas="", modelo_arquivo="")

    assert caminhos.caminho_da_nota(configuracao, nota, empresa_ativa) == ([], nota.chave)


@pytest.mark.django_db
def test_nivel_que_fica_vazio_apos_normalizar_vira_sublinhado(empresa_ativa):
    nota = nota_avulsa(1, numero_nfse="")
    configuracao = ConfiguracaoDrive(
        modelo_subpastas="{numero_nfse}/{ano}", modelo_arquivo="{chave}"
    )

    niveis, _ = caminhos.caminho_da_nota(configuracao, nota, empresa_ativa)

    assert niveis == ["_", "2026"]


@pytest.mark.django_db
def test_pre_visualizacao_mostra_pasta_arquivos_e_evento(empresa_ativa):
    nota = nota_avulsa(123)
    configuracao = ConfiguracaoDrive(
        modelo_subpastas="{ano}/{mes}", modelo_arquivo="NFSe {numero_nfse} - {chave}"
    )

    previa = caminhos.pre_visualizar(configuracao, nota, empresa_ativa)

    assert previa["pasta"] == "2026/11"
    assert previa["arquivos"] == [
        f"2026/11/NFSe 123 - {nota.chave}.xml",
        f"2026/11/NFSe 123 - {nota.chave}.pdf",
    ]
    assert previa["evento"].endswith("_cancelamento.xml")
