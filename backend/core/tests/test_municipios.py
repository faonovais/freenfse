"""Municípios: integridade do arquivo versionado do IBGE, comando de carga e validação do código."""

import hashlib
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command

from core.models import Municipio
from core.municipios import ARQUIVO_PADRAO, UF_POR_CODIGO, ErroNoArquivoDeMunicipios, ler_arquivo
from core.services import municipios

# SHA-256 registrado em core/dados/LEIAME.md: mudar o arquivo exige atualizar os dois.
SHA256_DO_ARQUIVO = "de3ce3f6e34ff52bfa83c05ed068d5e8cc95aa35321fcdd8b9320edc16b9a5d6"
# Códigos que o próprio IBGE atribuiu fora da regra do dígito verificador.
DV_IRREGULAR_NO_IBGE = {
    "2201919", "2201988", "2202251", "2611533", "3117836",
    "3152131", "4305871", "5203939", "5203962",
}  # fmt: skip


def _digito_verificador(seis):
    soma = 0
    for posicao, digito in enumerate(seis):
        produto = int(digito) * (1 if posicao % 2 == 0 else 2)
        soma += produto // 10 + produto % 10
    return (10 - soma % 10) % 10


def test_arquivo_bate_com_o_sha256_documentado():
    assert hashlib.sha256(ARQUIVO_PADRAO.read_bytes()).hexdigest() == SHA256_DO_ARQUIVO
    assert SHA256_DO_ARQUIVO in (ARQUIVO_PADRAO.parent / "LEIAME.md").read_text(encoding="utf-8")


def test_arquivo_tem_todos_os_municipios_e_ufs():
    linhas = ler_arquivo()

    assert len(linhas) == 5571
    assert len({codigo for codigo, _, _ in linhas}) == 5571
    assert {uf for _, _, uf in linhas} == set(UF_POR_CODIGO.values())
    assert len(UF_POR_CODIGO) == 27


def test_digito_verificador_confere_exceto_nos_codigos_irregulares_do_ibge():
    irregulares = {
        codigo
        for codigo, _, _ in ler_arquivo()
        if int(codigo[6]) != _digito_verificador(codigo[:6])
    }

    assert irregulares == DV_IRREGULAR_NO_IBGE


@pytest.mark.parametrize(
    ("codigo", "nome", "uf"),
    [
        ("3550308", "São Paulo", "SP"),
        ("3304557", "Rio de Janeiro", "RJ"),
        ("5300108", "Brasília", "DF"),
        ("1721000", "Palmas", "TO"),
        ("2101400", "Balsas", "MA"),
        ("2211001", "Teresina", "PI"),
        ("2919553", "Luís Eduardo Magalhães", "BA"),
    ],
)
def test_municipios_conhecidos_conferem(codigo, nome, uf):
    assert (codigo, nome, uf) in ler_arquivo()


@pytest.mark.django_db
def test_comando_carrega_e_e_idempotente():
    saida = StringIO()
    call_command("carregar_municipios", stdout=saida)
    call_command("carregar_municipios", stdout=saida)

    assert Municipio.objects.count() == 5571
    assert str(Municipio.objects.get(codigo="2101400")) == "Balsas/MA (2101400)"
    assert "5571 novos" in saida.getvalue().splitlines()[0]
    assert "0 novos" in saida.getvalue().splitlines()[1]


@pytest.mark.django_db
def test_comando_preenche_o_nome_de_busca_sem_acento():
    call_command("carregar_municipios", stdout=StringIO())

    assert Municipio.objects.get(codigo="3550308").nome_busca == "sao paulo"
    assert Municipio.objects.get(codigo="2919553").nome_busca == "luis eduardo magalhaes"


@pytest.mark.django_db
def test_comando_atualiza_nome_alterado():
    Municipio.objects.create(codigo="2101400", nome="Nome Antigo", uf="MA")

    call_command("carregar_municipios", stdout=StringIO())

    assert Municipio.objects.get(codigo="2101400").nome == "Balsas"


@pytest.mark.django_db
def test_verificar_nao_grava():
    call_command("carregar_municipios", "--verificar", stdout=StringIO())

    assert Municipio.objects.count() == 0


def _arquivo(tmp_path, conteudo):
    caminho = tmp_path / "municipios.csv"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        ("codigo,nome\n", "Cabeçalho"),
        ("codigo_ibge,nome,uf\n123,X,SP\n", "código IBGE inválido"),
        ("codigo_ibge,nome,uf\n3550308,A,SP\n3550308,B,SP\n", "repetido"),
        ("codigo_ibge,nome,uf\n3550308,A,RJ\n", "UF"),
        ("codigo_ibge,nome,uf\n3550308, ,SP\n", "nome vazio"),
    ],
)
def test_arquivo_malformado_e_recusado(tmp_path, conteudo, trecho):
    with pytest.raises(ErroNoArquivoDeMunicipios, match=trecho):
        ler_arquivo(_arquivo(tmp_path, conteudo))


def test_comando_informa_arquivo_invalido(tmp_path):
    with pytest.raises(CommandError, match="Cabeçalho"):
        call_command("carregar_municipios", arquivo=str(_arquivo(tmp_path, "x\n")))


@pytest.mark.django_db
class TestValidarCodigoIbge:
    def test_aceita_codigo_existente_mesmo_com_mascara(self, municipios_basicos):
        assert municipios.validar_codigo_ibge("2101400") == "2101400"
        assert municipios.validar_codigo_ibge(" 2101400 ") == "2101400"

    @pytest.mark.parametrize("valor", ["123", "", None, "21014000", "abc"])
    def test_recusa_formato_invalido(self, municipios_basicos, valor):
        with pytest.raises(ValidationError) as erro:
            municipios.validar_codigo_ibge(valor)
        assert erro.value.code == "ibge"

    def test_recusa_codigo_inexistente(self, municipios_basicos):
        with pytest.raises(ValidationError, match="não encontrado"):
            municipios.validar_codigo_ibge("9999999")

    def test_tabela_vazia_orienta_a_carregar(self):
        with pytest.raises(ValidationError) as erro:
            municipios.validar_codigo_ibge("2101400")
        assert erro.value.code == "municipios_nao_carregados"
        assert "carregar_municipios" in erro.value.messages[0]

    def test_obter(self, municipios_basicos):
        assert municipios.obter("2101400").nome == "Balsas"
        assert municipios.obter("9999999") is None
