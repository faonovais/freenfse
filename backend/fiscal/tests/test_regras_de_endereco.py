"""Endereços do tomador e do destinatário pelo `cIndOp` (E0239, E0243, E0919, E0901; issue #33).

A primeira parte testa a função pura (`regras_de_endereco.avaliar`) em tabelas, sem banco; a
segunda, a aplicação na prévia, na solicitação e na execução da emissão. O local do fornecimento
de cada indicador sai do Anexo VII (`local_fornecimento`); ADR 0011.
"""

import json

import pytest
from django.core.exceptions import ValidationError

from cadastros.models import Pessoa
from conftest import cnpj_de_teste, cpf_de_teste
from fiscal.referencias import local_fornecimento
from fiscal.services import regras_de_endereco as regras

TABELA = json.loads(local_fornecimento.ARQUIVO.read_text(encoding="utf-8"))["indicadores"]
POR_CLASSE = {
    classe: sorted(c for c, r in TABELA.items() if r["classe"] == classe)
    for classe in ("adquirente", "destinatario", "outro")
}
ADQUIRENTE, DESTINATARIO, OUTRO = "100301", "100302", "030101"  # um de cada local
FORA_DA_TABELA = "999999"

# -- pessoas (snapshots como a nota os guarda) ------------------------------------------------


def _pessoa(**ajustes):
    return {
        "tipo": "pj",
        "documento": cnpj_de_teste("112223330002"),
        "nif": "",
        "motivo_sem_nif": None,
        "nome": "PESSOA FICTICIA LTDA",
        "logradouro": "Rua das Flores",
        "numero": "100",
        "complemento": "",
        "bairro": "Centro",
        "codigo_municipio": "2903201",
        "cep": "47800000",
        "pais": "",
        "codigo_postal": "",
        "cidade": "",
        "estado": "",
        **ajustes,
    }


PJ = _pessoa()
PF = _pessoa(tipo="pf", documento=cpf_de_teste("529982247"), nome="PESSOA FISICA FICTICIA")
ESTRANGEIRO = _pessoa(
    tipo="estrangeiro",
    documento="",
    nif="NIF-123456",
    nome="EMPRESA NO EXTERIOR",
    logradouro="Main Street",
    numero="10",
    bairro="Downtown",
    codigo_municipio="",
    cep="",
    pais="US",
    codigo_postal="10001",
    cidade="New York",
    estado="NY",
)
SEM_ENDERECO = _pessoa(logradouro="", numero="", bairro="", codigo_municipio="", cep="")
CASOS_QUE_NAO_SERVEM = {
    "estrangeiro com NIF": (ESTRANGEIRO, "estrangeiro"),
    "sem endereço": (SEM_ENDERECO, "endereço incompleto"),
    "sem logradouro": (_pessoa(logradouro=""), "o logradouro"),
    "sem número": (_pessoa(numero=""), "o número"),
    "sem bairro": (_pessoa(bairro=""), "o bairro"),
    "CEP curto": (_pessoa(cep="4780000"), "o CEP"),
    "sem CEP": (_pessoa(cep=""), "o CEP"),
    "sem município": (_pessoa(codigo_municipio=""), "o município"),
    "município de 6 dígitos": (_pessoa(codigo_municipio="290320"), "o município"),
    "PJ sem CNPJ": (_pessoa(documento=""), "CNPJ"),
    "PJ com CNPJ inválido": (_pessoa(documento="11222333000199"), "CNPJ"),
    "PF sem CPF": (_pessoa(tipo="pf", documento=""), "CPF"),
    "PF com CPF inválido": (_pessoa(tipo="pf", documento="52998224700"), "CPF"),
    "endereço no exterior": (_pessoa(pais="US", cidade="Miami"), "exterior"),
    "tipo desconhecido": (_pessoa(tipo=""), "nem jurídica"),
}


def _avaliar(
    codigo, ind_dest, *, tomador=PJ, destinatario=None, exige_grupo=True
) -> regras.Resultado:
    return regras.avaliar(
        exige_grupo=exige_grupo,
        codigo_indicador=codigo,
        indicador_destinatario=ind_dest,
        tomador=tomador,
        destinatario=destinatario,
    )


def _reprovadas(resultado):
    return [(p.regra, p.campo) for p in resultado.pendencias]


# -- quem atende "CPF ou CNPJ e endereço nacional" -------------------------------------------


@pytest.mark.parametrize("pessoa", [PJ, PF], ids=["pessoa jurídica", "pessoa física"])
def test_pessoa_nacional_com_documento_e_endereco_completo_atende(pessoa):
    assert regras.problemas_da_pessoa(pessoa) == []


@pytest.mark.parametrize(
    ("pessoa", "trecho"), CASOS_QUE_NAO_SERVEM.values(), ids=list(CASOS_QUE_NAO_SERVEM)
)
def test_pessoa_que_nao_atende_diz_o_que_falta(pessoa, trecho):
    problemas = regras.problemas_da_pessoa(pessoa)

    assert problemas and trecho in " ".join(problemas)


def test_ninguem_informado_nao_atende():
    assert regras.problemas_da_pessoa(None) == ["não foi informado"]
    assert regras.problemas_da_pessoa({}) == ["não foi informado"]


# -- E0239: local = endereço do tomador/adquirente (vale com indDest 0 e 1) -------------------


@pytest.mark.parametrize("ind_dest", [0, 1])
@pytest.mark.parametrize(
    "tomador", [ESTRANGEIRO, SEM_ENDERECO, _pessoa(cep=""), _pessoa(documento="")]
)
def test_e0239_barra_tomador_sem_cpf_cnpj_ou_sem_endereco_nacional(ind_dest, tomador):
    resultado = _avaliar(ADQUIRENTE, ind_dest, tomador=tomador, destinatario=PJ)

    assert _reprovadas(resultado) == [("E0239", "tomador")]


@pytest.mark.parametrize("ind_dest", [0, 1])
@pytest.mark.parametrize("tomador", [PJ, PF], ids=["PJ", "PF"])
def test_e0239_aceita_tomador_pj_ou_pf_nacional_completo(ind_dest, tomador):
    resultado = _avaliar(ADQUIRENTE, ind_dest, tomador=tomador, destinatario=PJ)

    assert resultado.pendencias == [] and resultado.avisos == []


@pytest.mark.parametrize("ind_dest", [0, 1])
def test_e0239_nao_olha_o_destinatario(ind_dest):
    """O endereço que vale é o do tomador: destinatário ruim ou ausente não bloqueia aqui."""
    resultado = _avaliar(ADQUIRENTE, ind_dest, tomador=PJ, destinatario=ESTRANGEIRO)

    assert resultado.pendencias == []


# -- E0243: local = endereço do destinatário e indDest = 0 (o tomador é o destinatário) -------


@pytest.mark.parametrize(
    "tomador", [ESTRANGEIRO, SEM_ENDERECO, _pessoa(cep=""), _pessoa(documento="")]
)
def test_e0243_barra_tomador_sem_cpf_cnpj_ou_sem_endereco_nacional(tomador):
    resultado = _avaliar(DESTINATARIO, 0, tomador=tomador)

    assert _reprovadas(resultado) == [("E0243", "tomador")]


@pytest.mark.parametrize("tomador", [PJ, PF], ids=["PJ", "PF"])
def test_e0243_aceita_tomador_nacional_completo(tomador):
    assert _avaliar(DESTINATARIO, 0, tomador=tomador).pendencias == []


# -- E0919: local = endereço do destinatário e indDest = 1 (outra pessoa) ---------------------


@pytest.mark.parametrize(
    "destinatario",
    [None, ESTRANGEIRO, SEM_ENDERECO, _pessoa(bairro=""), _pessoa(documento="")],
    ids=["ausente", "estrangeiro", "sem endereço", "endereço incompleto", "sem CNPJ"],
)
def test_e0919_barra_destinatario_ausente_estrangeiro_ou_sem_endereco_nacional(destinatario):
    resultado = _avaliar(DESTINATARIO, 1, tomador=PJ, destinatario=destinatario)

    assert _reprovadas(resultado) == [("E0919", "destinatario")]


@pytest.mark.parametrize("destinatario", [PJ, PF], ids=["PJ", "PF"])
def test_e0919_aceita_destinatario_nacional_completo(destinatario):
    assert _avaliar(DESTINATARIO, 1, tomador=PJ, destinatario=destinatario).pendencias == []


def test_e0919_nao_olha_o_tomador():
    """Com indDest = 1 quem precisa de endereço é o destinatário; o tomador pode até ser de fora."""
    assert _avaliar(DESTINATARIO, 1, tomador=ESTRANGEIRO, destinatario=PJ).pendencias == []


def test_e0243_nao_olha_o_destinatario_e_e0919_nao_vale_com_ind_dest_zero():
    resultado = _avaliar(DESTINATARIO, 0, tomador=PJ, destinatario=ESTRANGEIRO)

    assert resultado.pendencias == []


# -- tabela completa: todo cIndOp do Anexo VII pela sua classe --------------------------------


@pytest.mark.parametrize("codigo", POR_CLASSE["adquirente"])
def test_todo_indicador_de_adquirente_exige_o_endereco_do_tomador(codigo):
    for ind_dest in (0, 1):
        resultado = _avaliar(codigo, ind_dest, tomador=ESTRANGEIRO, destinatario=PJ)
        assert _reprovadas(resultado) == [("E0239", "tomador")]


@pytest.mark.parametrize("codigo", POR_CLASSE["destinatario"])
def test_todo_indicador_de_destinatario_exige_o_endereco_de_quem_e_destinatario(codigo):
    com_ind_dest_0 = _avaliar(codigo, 0, tomador=ESTRANGEIRO, destinatario=PJ)
    com_ind_dest_1 = _avaliar(codigo, 1, tomador=PJ, destinatario=ESTRANGEIRO)
    assert _reprovadas(com_ind_dest_0) == [("E0243", "tomador")]
    assert _reprovadas(com_ind_dest_1) == [("E0919", "destinatario")]


@pytest.mark.parametrize("codigo", POR_CLASSE["outro"])
def test_indicador_sem_endereco_de_pessoa_nunca_bloqueia(codigo):
    for ind_dest in (0, 1):
        for tomador, destinatario in ((ESTRANGEIRO, None), (SEM_ENDERECO, ESTRANGEIRO)):
            resultado = _avaliar(codigo, ind_dest, tomador=tomador, destinatario=destinatario)
            assert resultado.pendencias == []


def test_a_classificacao_tem_4_adquirentes_7_destinatarios_e_29_outros():
    assert [len(POR_CLASSE[c]) for c in ("adquirente", "destinatario", "outro")] == [4, 7, 29]


# -- sem o grupo de IBS/CBS nenhuma regra se aplica -------------------------------------------


@pytest.mark.parametrize("codigo", [ADQUIRENTE, DESTINATARIO, OUTRO, FORA_DA_TABELA, "130201"])
@pytest.mark.parametrize("ind_dest", [0, 1, None])
def test_sem_o_grupo_de_ibs_cbs_nada_se_aplica(codigo, ind_dest):
    resultado = _avaliar(
        codigo, ind_dest, tomador=ESTRANGEIRO, destinatario=ESTRANGEIRO, exige_grupo=False
    )

    assert resultado.pendencias == [] and resultado.avisos == []


# -- E0901: cIndOp fora da tabela --------------------------------------------------------------


@pytest.mark.parametrize("codigo", [FORA_DA_TABELA, "123456", "", None, "10030"])
def test_indicador_fora_da_tabela_bloqueia_com_o_codigo_da_regra(codigo):
    resultado = _avaliar(codigo, 0, tomador=PJ)

    assert _reprovadas(resultado) == [("E0901", "ibs_cbs")]
    assert "Anexo VII" in resultado.pendencias[0].mensagem


def test_indicador_que_consta_da_tabela_nao_dispara_e0901():
    for codigo in TABELA:
        assert ("E0901", "ibs_cbs") not in _reprovadas(_avaliar(codigo, 0, tomador=PJ))


# -- 130201: o texto cita o adquirente, a coluna estruturada não --------------------------------


@pytest.mark.parametrize(
    "tomador", [ESTRANGEIRO, SEM_ENDERECO, None], ids=["exterior", "sem endereço", "ausente"]
)
@pytest.mark.parametrize("ind_dest", [0, 1])
def test_130201_avisa_sem_bloquear_quando_o_tomador_nao_atende(tomador, ind_dest):
    resultado = _avaliar("130201", ind_dest, tomador=tomador, destinatario=None)

    assert resultado.pendencias == []
    assert len(resultado.avisos) == 1
    assert resultado.avisos[0].startswith(
        "O texto do Anexo VII indica o endereço do adquirente para este indicador; confira se o "
        "tomador tem CPF/CNPJ e endereço nacional, para evitar a rejeição E0239"
    )


@pytest.mark.parametrize("tomador", [PJ, PF], ids=["PJ", "PF"])
def test_130201_nao_avisa_com_tomador_completo(tomador):
    resultado = _avaliar("130201", 0, tomador=tomador)

    assert resultado.pendencias == [] and resultado.avisos == []


@pytest.mark.parametrize("codigo", [c for c in TABELA if c != "130201"])
def test_so_o_130201_gera_aviso_de_texto(codigo):
    resultado = _avaliar(codigo, 0, tomador=ESTRANGEIRO, destinatario=PJ)

    assert resultado.avisos == []


# -- mensagens: regra, indicador, quem e o que corrigir ----------------------------------------


def test_mensagem_da_e0239_e_didatica():
    [pendencia] = _avaliar(ADQUIRENTE, 0, tomador=_pessoa(bairro="", cep="")).pendencias

    mensagem = pendencia.mensagem
    assert "E0239" in mensagem and "100301" in mensagem
    assert "tomador/adquirente" in mensagem and "“PESSOA FICTICIA LTDA”" in mensagem
    assert "falta o bairro, o CEP" in mensagem
    assert "Escolha outro tomador" in mensagem and "troque o indicador" in mensagem


def test_mensagem_da_e0243_diz_que_o_destinatario_e_o_proprio_tomador():
    [pendencia] = _avaliar(DESTINATARIO, 0, tomador=ESTRANGEIRO).pendencias

    assert "E0243" in pendencia.mensagem and "próprio tomador" in pendencia.mensagem
    assert "é estrangeiro" in pendencia.mensagem


def test_mensagem_da_e0919_pede_o_destinatario_quando_ele_nao_foi_informado():
    [pendencia] = _avaliar(DESTINATARIO, 1, tomador=PJ, destinatario=None).pendencias

    assert "E0919" in pendencia.mensagem and "não foi informado" in pendencia.mensagem
    assert "Escolha o destinatário no cadastro de pessoas" in pendencia.mensagem


def test_o_resultado_pode_ter_pendencia_e_aviso_sem_se_misturarem():
    resultado = _avaliar(ADQUIRENTE, 0, tomador=ESTRANGEIRO)

    assert len(resultado.pendencias) == 1 and resultado.avisos == []


# -- consistência com o cadastro de pessoas ----------------------------------------------------


@pytest.mark.django_db
class TestConsistenciaComOCadastro:
    """O que o cadastro aceita gravar como PF/PJ atende à regra; o que a regra recusa, não grava."""

    @pytest.fixture(autouse=True)
    def _municipios(self, municipios_basicos):
        pass

    @pytest.mark.parametrize(
        ("pessoa", "grava"),
        [(PJ, True), (PF, True)]
        + [
            (p, False)
            for nome, (p, _) in CASOS_QUE_NAO_SERVEM.items()
            if nome != "estrangeiro com NIF"
        ],
        ids=["PJ", "PF"] + [n for n in CASOS_QUE_NAO_SERVEM if n != "estrangeiro com NIF"],
    )
    def test_quem_o_cadastro_aceita_atende_e_quem_atende_o_cadastro_aceita(self, pessoa, grava):
        campos = {k: v for k, v in pessoa.items() if k != "tipo"}
        candidata = Pessoa(tipo=pessoa["tipo"] or "x", **campos)

        try:
            candidata.clean()
            gravou = True
        except ValidationError:
            gravou = False

        assert gravou == grava
        assert (regras.problemas_da_pessoa(pessoa) == []) == grava
