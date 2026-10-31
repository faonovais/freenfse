"""IBS/CBS por empresa (issue #20, ADR 0007): padrão da empresa, ajuste pontual e o que vai na DPS.

A opção pelo IBS/CBS e o indicador da operação (cIndOp) são da empresa; a classificação (NBS, CST
e cClassTrib) é do serviço. A nota herda o padrão ao nascer e pode ajustá-lo pontualmente.
O comportamento de IBS/CBS da Fase 3 não tinha testes: este arquivo cobre também esse legado.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django_tenants.utils import schema_context
from lxml import etree

from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import gateway
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import criar_cadastros_de_teste, preparar_empresa_para_emitir

pytestmark = pytest.mark.django_db
HOJE = dt.date(2026, 10, 31)
NS = "{http://www.sped.fazenda.gov.br/nfse}"
NOTAS = "/api/fiscal/notas/"
PARAMETROS = "/api/fiscal/parametros/"
PADRAO = "010101"
OUTRO = "020202"
# Origem de cada campo quando tudo vem da empresa (a nota e o modelo não definiram nada).
ORIGENS_EMPRESA = {
    "informar": "empresa",
    "codigo_indicador_operacao": "empresa",
    "indicador_destinatario": "empresa",
}


# -- apoio ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """O município emissor é validado pela tabela de municípios (chamadas de parâmetros)."""


def _padrao_da_empresa(informar=True, indicador=PADRAO):
    ParametrosFiscais.objects.update(
        ibs_cbs_informar=informar, ibs_cbs_indicador_operacao=indicador
    )


def _dados(tomador, servico, **extra):
    return {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": dt.date(2026, 10, 1),
        "valores": {"servico": "1000.00"},
        **extra,
    }


@pytest.fixture
def cadastros(empresa_pronta):
    """Tomador, serviço **sem** classificação e serviço **com** classificação de IBS/CBS."""
    from cadastros.models import Servico

    tomador, sem = criar_cadastros_de_teste()
    com = Servico.objects.create(
        nome="Consultoria com IBS/CBS",
        descricao="Consultoria em gestão agrícola.",
        codigo_tributacao_nacional="170101",
        codigo_tributacao_municipal="002",
        nbs="113011000",
        cst_ibs_cbs="200",
        c_class_trib="200003",
        aliquota_iss=Decimal("2.00"),
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    return tomador, sem, com


def _preparar(tomador, servico, **extra):
    return servico_nfse.preparar(_dados(tomador, servico, **extra), hoje=HOJE)


def _erros(tomador, servico, **extra):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _preparar(tomador, servico, **extra)
    return erro.value.erros


# -- o padrão da empresa --------------------------------------------------------------------


def test_empresa_sem_opcao_e_servico_sem_classificacao_segue_sem_grupo_e_sem_aviso(cadastros):
    tomador, sem, _ = cadastros

    preparo = _preparar(tomador, sem)

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["na_dps"] is False
    assert preparo.ibs_cbs_dps["motivo"] == "O serviço não tem classificação de IBS/CBS."
    assert not any("IBS/CBS" in aviso for aviso in preparo.avisos)


def test_empresa_sem_opcao_e_servico_com_classificacao_avisa_que_vai_sem_grupo(cadastros):
    tomador, _, com = cadastros

    preparo = _preparar(tomador, com)

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["motivo"] == "A empresa não informa o IBS/CBS (parâmetros fiscais)."
    assert any("a empresa não informa IBS/CBS" in aviso for aviso in preparo.avisos)


def test_nota_herda_o_padrao_da_empresa_e_a_classificacao_do_servico(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()

    preparo = _preparar(tomador, com)

    assert preparo.complementos["ibs_cbs"] == {
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
        "origens": ORIGENS_EMPRESA,
    }
    assert preparo.ibs_cbs_dps == {
        "na_dps": True,
        "motivo": None,
        "origens": ORIGENS_EMPRESA,
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
        "nbs": "113011000",
        "cst": "200",
        "c_class_trib": "200003",
    }
    assert not any("IBS/CBS" in aviso for aviso in preparo.avisos)


def test_opcao_desligada_ignora_o_indicador_guardado(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa(informar=False)  # o indicador fica guardado, mas a opção está desligada

    assert _preparar(tomador, com).complementos["ibs_cbs"] is None


def test_empresa_com_opcao_e_servico_sem_classificacao_avisa_para_completar_o_cadastro(cadastros):
    tomador, sem, _ = cadastros
    _padrao_da_empresa()

    preparo = _preparar(tomador, sem)

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["na_dps"] is False
    assert any("Complete o cadastro do serviço" in aviso for aviso in preparo.avisos)


# -- o ajuste pontual -----------------------------------------------------------------------


def test_ajuste_pontual_vale_mais_que_o_padrao_da_empresa(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()

    preparo = _preparar(
        tomador,
        com,
        ibs_cbs={"codigo_indicador_operacao": OUTRO, "indicador_destinatario": "1"},
    )

    assert preparo.complementos["ibs_cbs"] == {
        "codigo_indicador_operacao": OUTRO,
        "indicador_destinatario": 1,
        "origens": {
            "informar": "nota",  # indicar o cIndOp na nota vale como "informar"
            "codigo_indicador_operacao": "nota",
            "indicador_destinatario": "nota",
        },
    }
    assert preparo.ibs_cbs_dps["origens"]["codigo_indicador_operacao"] == "nota"


def test_ajuste_pontual_so_do_destinatario_mantem_o_indicador_da_empresa(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()

    grupo = _preparar(tomador, com, ibs_cbs={"indicador_destinatario": 1}).complementos["ibs_cbs"]

    assert (grupo["codigo_indicador_operacao"], grupo["indicador_destinatario"]) == (PADRAO, 1)
    assert grupo["origens"] == {**ORIGENS_EMPRESA, "indicador_destinatario": "nota"}  # por campo


def test_nao_informar_nesta_nota_tira_o_grupo_mesmo_com_o_padrao_ligado(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()

    preparo = _preparar(tomador, com, ibs_cbs={"informar": False})

    assert preparo.complementos["ibs_cbs"] is None
    assert preparo.ibs_cbs_dps["motivo"] == "Você escolheu não informar o IBS/CBS nesta nota."
    assert preparo.ibs_cbs_dps["na_dps"] is False


def test_ajuste_pontual_funciona_mesmo_com_a_opcao_da_empresa_desligada(cadastros):
    tomador, _, com = cadastros

    grupo = _preparar(
        tomador, com, ibs_cbs={"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 0}
    ).complementos["ibs_cbs"]

    assert grupo["codigo_indicador_operacao"] == OUTRO
    assert grupo["origens"]["codigo_indicador_operacao"] == "nota"
    assert grupo["origens"]["informar"] == "nota"  # sem a opção da empresa, a nota decidiu


def test_pedir_para_informar_sem_nenhum_indicador_e_erro_didatico(cadastros):
    tomador, _, com = cadastros

    erros = _erros(tomador, com, ibs_cbs={"informar": True})

    assert "desta nota, do modelo ou dos parâmetros fiscais da empresa" in erros["ibs_cbs"]


def test_pedir_para_informar_usa_o_padrao_da_empresa_quando_ele_existe(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()

    grupo = _preparar(tomador, com, ibs_cbs={"informar": True}).complementos["ibs_cbs"]

    assert grupo["codigo_indicador_operacao"] == PADRAO
    assert grupo["origens"] == {**ORIGENS_EMPRESA, "informar": "nota"}


def test_classificacao_sem_nbs_nao_conta_como_servico_classificado(cadastros):
    """A NBS é obrigatória quando há o grupo (E0322): sem ela o serviço não tem classificação."""
    from cadastros.models import Servico

    tomador, _, com = cadastros
    Servico.objects.filter(pk=com.pk).update(nbs="")  # CST e cClassTrib sem NBS (dado incompleto)
    com.refresh_from_db()
    _padrao_da_empresa()

    preparo = _preparar(tomador, com)

    assert preparo.complementos["ibs_cbs"] is None
    assert any("Complete o cadastro do serviço" in aviso for aviso in preparo.avisos)
    erros = _erros(tomador, com, ibs_cbs={"codigo_indicador_operacao": PADRAO})
    assert "NBS, CST e classificação do IBS/CBS" in erros["ibs_cbs"]


# -- validações -----------------------------------------------------------------------------


@pytest.mark.parametrize("indicador", ["12345", "1234567", "01010A", "010 101"])
def test_indicador_da_nota_precisa_ter_6_digitos(cadastros, indicador):
    tomador, _, com = cadastros

    erros = _erros(tomador, com, ibs_cbs={"codigo_indicador_operacao": indicador})

    assert erros["ibs_cbs"] == "O código do indicador da operação tem 6 dígitos."


@pytest.mark.parametrize("destinatario", [2, "2", -1, "x"])
def test_indicador_do_destinatario_so_pode_ser_0_ou_1(cadastros, destinatario):
    tomador, _, com = cadastros

    erros = _erros(
        tomador,
        com,
        ibs_cbs={"codigo_indicador_operacao": PADRAO, "indicador_destinatario": destinatario},
    )

    assert "próprio tomador (0 ou 1)" in erros["ibs_cbs"]


def test_destinatario_ausente_vale_zero_o_proprio_tomador(cadastros):
    tomador, _, com = cadastros

    grupo = _preparar(tomador, com, ibs_cbs={"codigo_indicador_operacao": PADRAO}).complementos[
        "ibs_cbs"
    ]

    assert grupo["indicador_destinatario"] == 0


def test_indicador_corrompido_da_empresa_nao_chega_a_dps(cadastros):
    """Mesmo que o dado da empresa fuja da validação (ex.: edição direta no banco)."""
    tomador, _, com = cadastros
    _padrao_da_empresa(indicador="12")

    assert _erros(tomador, com)["ibs_cbs"] == "O código do indicador da operação tem 6 dígitos."


def test_ajuste_pontual_exige_classificacao_no_servico(cadastros):
    tomador, sem, _ = cadastros

    erros = _erros(tomador, sem, ibs_cbs={"codigo_indicador_operacao": PADRAO})

    assert "NBS, CST e classificação do IBS/CBS" in erros["ibs_cbs"]


# -- as três origens e a prioridade: nota > modelo > empresa --------------------------------


def _empresa(informar=True, indicador=PADRAO, destinatario=0):
    return SimpleNamespace(
        ibs_cbs_informar=informar,
        ibs_cbs_indicador_operacao=indicador,
        ibs_cbs_indicador_destinatario=destinatario,
    )


def _resolver(nota=None, modelo=None, empresa=None):
    valores, origens, erro = servico_nfse.resolver_ibs_cbs(nota, modelo, empresa or _empresa())
    assert erro is None, erro
    return valores, origens


def test_sem_nota_nem_modelo_tudo_vem_da_empresa():
    valores, origens = _resolver()

    assert valores == {
        "informar": True,
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
    }
    assert origens == ORIGENS_EMPRESA


def test_o_modelo_vale_mais_que_a_empresa_campo_a_campo():
    valores, origens = _resolver(modelo={"codigo_indicador_operacao": OUTRO})

    assert valores["codigo_indicador_operacao"] == OUTRO
    # Só o campo que o modelo definiu muda de origem; o resto continua herdado da empresa.
    assert origens == {
        "informar": "modelo",  # indicar o cIndOp no modelo vale como "informar"
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "empresa",
    }


def test_a_nota_vale_mais_que_o_modelo_que_vale_mais_que_a_empresa():
    valores, origens = _resolver(
        nota={"indicador_destinatario": 1},
        modelo={"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 0},
        empresa=_empresa(indicador="030303", destinatario=0),
    )

    assert valores == {
        "informar": True,
        "codigo_indicador_operacao": OUTRO,
        "indicador_destinatario": 1,
    }
    assert origens == {
        "informar": "modelo",
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "nota",
    }


def test_cada_nivel_pode_dizer_para_nao_informar_e_o_mais_forte_decide():
    assert _resolver(nota={"informar": False})[0]["informar"] is False
    assert _resolver(nota={"informar": False})[1]["informar"] == "nota"
    assert _resolver(modelo={"informar": False})[1]["informar"] == "modelo"
    # A nota pode voltar a informar o que o modelo dispensou, e o modelo o que a empresa dispensou.
    assert _resolver(nota={"informar": True}, modelo={"informar": False})[0]["informar"] is True
    desligada = _empresa(informar=False)
    assert _resolver(modelo={"informar": True}, empresa=desligada)[0]["informar"] is True
    assert _resolver(nota={"informar": False}, modelo={"informar": True})[0]["informar"] is False


def test_o_indicador_guardado_pela_empresa_vale_para_o_modelo_mesmo_com_a_opcao_desligada():
    valores, origens = _resolver(modelo={"informar": True}, empresa=_empresa(informar=False))

    assert valores["codigo_indicador_operacao"] == PADRAO
    assert origens["codigo_indicador_operacao"] == "empresa"
    assert origens["informar"] == "modelo"


def test_vazio_nao_define_nada_e_a_empresa_de_agora_e_que_vale():
    """Campo vazio herda; mudar a empresa muda o resultado na hora (nada foi copiado)."""
    modelo_que_herda = {
        "informar": None,
        "codigo_indicador_operacao": "",
        "indicador_destinatario": None,
    }

    antes = _resolver(modelo=modelo_que_herda, empresa=_empresa(indicador=PADRAO, destinatario=0))
    depois = _resolver(modelo=modelo_que_herda, empresa=_empresa(indicador=OUTRO, destinatario=1))

    assert antes[0]["codigo_indicador_operacao"] == PADRAO and antes[1] == ORIGENS_EMPRESA
    assert (
        depois[0]["codigo_indicador_operacao"] == OUTRO and depois[0]["indicador_destinatario"] == 1
    )
    assert depois[1] == ORIGENS_EMPRESA


@pytest.mark.parametrize("nivel", ["nota", "modelo"])
def test_destinatario_vazio_herda_da_empresa_em_vez_de_virar_erro(nivel):
    """A tela envia "" para "Herdar": não é valor inválido, é campo sem definição."""
    definicao = {"indicador_destinatario": ""}
    empresa = _empresa(destinatario=1)

    valores, origens = _resolver(
        nota=definicao if nivel == "nota" else None,
        modelo=definicao if nivel == "modelo" else None,
        empresa=empresa,
    )

    assert valores["indicador_destinatario"] == 1  # o da empresa, não 0 nem erro
    assert origens["indicador_destinatario"] == "empresa"
    # E o ajuste guardado na nota não leva o campo vazio.
    assert servico_nfse.ajuste_da_nota(definicao) is None


@pytest.mark.parametrize(
    ("nota", "trecho"),
    [
        ({"informar": "sim"}, "verdadeiro ou falso"),
        ({"indicador_destinatario": 2}, "próprio tomador (0 ou 1)"),
        ({"indicador_destinatario": "x"}, "próprio tomador (0 ou 1)"),
    ],
)
def test_valor_invalido_em_qualquer_nivel_e_recusado(nota, trecho):
    for nivel in ("nota", "modelo"):
        _, _, erro = servico_nfse.resolver_ibs_cbs(
            nota if nivel == "nota" else None,
            nota if nivel == "modelo" else None,
            _empresa(),
        )
        assert trecho in erro


def test_o_ajuste_da_nota_guardado_so_tem_o_que_a_nota_definiu():
    assert servico_nfse.ajuste_da_nota(None) is None
    assert servico_nfse.ajuste_da_nota({}) is None
    assert (
        servico_nfse.ajuste_da_nota(
            {"codigo_indicador_operacao": "", "indicador_destinatario": None}
        )
        is None
    )
    assert servico_nfse.ajuste_da_nota({"informar": False}) == {"informar": False}
    assert servico_nfse.ajuste_da_nota(
        {"codigo_indicador_operacao": OUTRO, "indicador_destinatario": "1"}
    ) == {
        "codigo_indicador_operacao": OUTRO,
        "indicador_destinatario": 1,
    }
    # Indicar o cIndOp não faz o "informar" virar ajuste guardado: ele só vale como efeito.
    assert "informar" not in servico_nfse.ajuste_da_nota({"codigo_indicador_operacao": OUTRO})


# -- snapshot: a nota guarda o que valia quando nasceu ---------------------------------------


def test_rascunho_guarda_o_padrao_de_quando_nasceu_e_so_muda_ao_ser_salvo_de_novo(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()
    nota = servico_nfse.criar_rascunho(_dados(tomador, com), usuario=None, hoje=HOJE)
    _padrao_da_empresa(indicador=OUTRO)  # a empresa muda o padrão depois

    nota.refresh_from_db()
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == PADRAO  # não muda sozinho

    servico_nfse.atualizar_rascunho(nota, _dados(tomador, com))  # salvar de novo refaz o snapshot
    nota.refresh_from_db()
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO


def test_substituta_leva_o_mesmo_grupo_da_original(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()
    original = servico_nfse.criar_rascunho(_dados(tomador, com), usuario=None, hoje=HOJE)
    # Uma nota autorizada, sem passar pela Sefin: a situação só muda pelas ações da nota.
    Nfse.objects.filter(pk=original.pk).update(situacao=Nfse.Situacao.AUTORIZADA, chave="1" * 50)
    original.refresh_from_db()
    _padrao_da_empresa(indicador=OUTRO)

    substituta = servico_nfse.criar_substituta(
        original, codigo_motivo="99", motivo="Correção dos dados da nota original.", usuario=None
    )

    assert substituta.complementos["ibs_cbs"]["codigo_indicador_operacao"] == PADRAO


# -- o que chega à DPS ----------------------------------------------------------------------


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return etree.fromstring(bytes(nota.xml_dps))


def test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico(
    empresa_pronta, cadastros, sefin
):
    tomador, _, com = cadastros
    _padrao_da_empresa()
    nota = servico_nfse.criar_rascunho(_dados(tomador, com), usuario=None, hoje=HOJE)

    raiz = _emitir(empresa_pronta, nota)

    grupo = raiz.find(f".//{NS}IBSCBS")
    assert grupo is not None
    assert grupo.findtext(f"{NS}cIndOp") == PADRAO
    assert grupo.findtext(f"{NS}indDest") == "0"
    # NT 009: CST e cClassTrib ficam direto em valores/trib (o gIBSCBS é da NT 004).
    assert grupo.findtext(f"{NS}valores/{NS}trib/{NS}CST") == "200"
    assert grupo.findtext(f"{NS}valores/{NS}trib/{NS}cClassTrib") == "200003"
    assert raiz.findtext(f".//{NS}cNBS") == "113011000"


def test_dps_assinada_leva_o_ajuste_pontual_e_nao_o_padrao(empresa_pronta, cadastros, sefin):
    tomador, _, com = cadastros
    _padrao_da_empresa()
    nota = servico_nfse.criar_rascunho(
        _dados(
            tomador,
            com,
            ibs_cbs={"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 1},
        ),
        usuario=None,
        hoje=HOJE,
    )

    grupo = _emitir(empresa_pronta, nota).find(f".//{NS}IBSCBS")

    assert (grupo.findtext(f"{NS}cIndOp"), grupo.findtext(f"{NS}indDest")) == (OUTRO, "1")


@pytest.mark.parametrize(
    "preparar_cenario",
    ["empresa_sem_opcao", "nota_sem_grupo"],
)
def test_dps_sem_o_grupo_quando_a_empresa_nao_informa_ou_a_nota_dispensa(
    empresa_pronta, cadastros, sefin, preparar_cenario
):
    tomador, _, com = cadastros
    extra = {}
    if preparar_cenario == "nota_sem_grupo":
        _padrao_da_empresa()
        extra = {"ibs_cbs": {"informar": False}}
    nota = servico_nfse.criar_rascunho(_dados(tomador, com, **extra), usuario=None, hoje=HOJE)

    raiz = _emitir(empresa_pronta, nota)

    assert raiz.find(f".//{NS}IBSCBS") is None


def test_montar_dps_ignora_a_origem_e_exige_a_classificacao_do_servico(cadastros):
    tomador, _, com = cadastros
    _padrao_da_empresa()
    nota = servico_nfse.criar_rascunho(_dados(tomador, com), usuario=None, hoje=HOJE)
    dados = servico_nfse.dados_da_dps(nota, empresa=nota_empresa(), numero=1)

    dps = gateway.montar_dps(dados)

    assert (dps.ibs_cbs.codigo_indicador_operacao, dps.ibs_cbs.indicador_destinatario) == (
        PADRAO,
        0,
    )
    assert (dps.ibs_cbs.cst, dps.ibs_cbs.codigo_classificacao) == ("200", "200003")


def nota_empresa():
    """Empresa mínima (só o CNPJ) para montar os dados da DPS."""
    from types import SimpleNamespace

    from conftest import CNPJ_A

    return SimpleNamespace(cnpj=CNPJ_A)


# -- parâmetros da empresa (API) ------------------------------------------------------------


@pytest.fixture
def api_admin(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
    return api_de(empresa_a)


def test_parametros_trazem_a_opcao_desligada_e_o_indicador_vazio_por_padrao(api_admin):
    corpo = api_admin.get(PARAMETROS).json()

    assert corpo["ibs_cbs_informar"] is False and corpo["ibs_cbs_indicador_operacao"] == ""


def test_administrador_liga_a_opcao_com_o_indicador_e_a_mudanca_e_auditada(api_admin):
    resposta = api_admin.patch(
        PARAMETROS, {"ibs_cbs_informar": True, "ibs_cbs_indicador_operacao": "010.101"}
    )

    assert resposta.status_code == 200, resposta.json()
    corpo = resposta.json()
    assert (corpo["ibs_cbs_informar"], corpo["ibs_cbs_indicador_operacao"]) == (True, PADRAO)
    alterados = LogAuditoria.objects.get(acao=LogAuditoria.Acao.PARAMETROS_ALTERADOS).detalhes[
        "alterados"
    ]
    assert alterados["ibs_cbs_informar"] == {"de": False, "para": True}
    assert alterados["ibs_cbs_indicador_operacao"]["para"] == PADRAO


def test_ligar_a_opcao_sem_indicador_e_recusado_com_a_explicacao(api_admin):
    resposta = api_admin.patch(PARAMETROS, {"ibs_cbs_informar": True})

    assert resposta.status_code == 400
    assert (
        "informe o indicador da operação padrão" in resposta.json()["ibs_cbs_indicador_operacao"][0]
    )
    assert api_admin.get(PARAMETROS).json()["ibs_cbs_informar"] is False  # nada foi gravado


def test_administrador_muda_o_destinatario_padrao_da_empresa(api_admin):
    corpo = api_admin.patch(PARAMETROS, {"ibs_cbs_indicador_destinatario": 1}).json()

    assert corpo["ibs_cbs_indicador_destinatario"] == 1
    assert api_admin.get(PARAMETROS).json()["ibs_cbs_indicador_destinatario"] == 1
    alterados = LogAuditoria.objects.get(acao=LogAuditoria.Acao.PARAMETROS_ALTERADOS).detalhes[
        "alterados"
    ]
    assert alterados["ibs_cbs_indicador_destinatario"] == {"de": 0, "para": 1}


def test_destinatario_padrao_da_empresa_so_aceita_0_ou_1(api_admin):
    assert api_admin.patch(PARAMETROS, {"ibs_cbs_indicador_destinatario": 2}).status_code == 400
    from django.core.exceptions import ValidationError

    invalido = ParametrosFiscais(ibs_cbs_indicador_destinatario=2)  # fora da API também
    with pytest.raises(ValidationError) as erro:
        invalido.clean()
    assert "ibs_cbs_indicador_destinatario" in erro.value.message_dict


@pytest.mark.parametrize("indicador", ["12345", "1234567"])
def test_indicador_padrao_da_empresa_tem_6_digitos(api_admin, indicador):
    resposta = api_admin.patch(PARAMETROS, {"ibs_cbs_indicador_operacao": indicador})

    assert resposta.status_code == 400
    assert resposta.json()["ibs_cbs_indicador_operacao"] == [
        "O indicador da operação tem 6 dígitos."
    ]


def test_desligar_a_opcao_guarda_o_indicador_para_quando_ligar_de_novo(api_admin):
    api_admin.patch(PARAMETROS, {"ibs_cbs_informar": True, "ibs_cbs_indicador_operacao": PADRAO})

    corpo = api_admin.patch(PARAMETROS, {"ibs_cbs_informar": False}).json()

    assert (corpo["ibs_cbs_informar"], corpo["ibs_cbs_indicador_operacao"]) == (False, PADRAO)


@pytest.mark.parametrize("perfil", [Perfil.EMISSOR, Perfil.CONSULTA, Perfil.FINANCEIRO])
def test_so_quem_edita_a_configuracao_muda_o_padrao_de_ibs_cbs(api_de, empresa_a, perfil):
    api = api_de(empresa_a, perfil)

    resposta = api.patch(
        PARAMETROS, {"ibs_cbs_informar": True, "ibs_cbs_indicador_operacao": PADRAO}
    )

    assert resposta.status_code == 403


def test_prontidao_expoe_o_padrao_da_empresa_para_a_tela_preencher(api_de, empresa_a):
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
    emissor = api_de(empresa_a, Perfil.EMISSOR)
    assert emissor.get(f"{NOTAS}prontidao/").json()["ibs_cbs"] == {
        "informar": False,
        "codigo_indicador_operacao": "",
        "indicador_destinatario": 0,
    }
    with schema_context(empresa_a.schema_name):
        _padrao_da_empresa()

    assert emissor.get(f"{NOTAS}prontidao/").json()["ibs_cbs"] == {
        "informar": True,
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
    }
    # O destinatário padrão também vem da empresa (a tela mostra "Herdar da empresa: …").
    with schema_context(empresa_a.schema_name):
        ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=1)

    assert emissor.get(f"{NOTAS}prontidao/").json()["ibs_cbs"]["indicador_destinatario"] == 1


# -- prévia e criação pela API --------------------------------------------------------------


@pytest.fixture
def emissor_com_servico(api_de, empresa_a):
    """Emissor da empresa A (pronta) e os ids do tomador e do serviço **com** classificação."""
    from cadastros.models import Servico

    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        tomador, _ = criar_cadastros_de_teste()
        servico = Servico.objects.create(
            nome="Consultoria com IBS/CBS",
            descricao="Consultoria em gestão agrícola.",
            codigo_tributacao_nacional="170101",
            codigo_tributacao_municipal="002",
            nbs="113011000",
            cst_ibs_cbs="200",
            c_class_trib="200003",
            aliquota_iss=Decimal("2.00"),
            vigencia_inicio=dt.date(2026, 1, 1),
        )
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    return api_de(empresa_a, Perfil.EMISSOR), corpo


def test_previa_mostra_o_que_vai_na_dps_com_a_origem(emissor_com_servico, empresa_a):
    api, corpo = emissor_com_servico
    with schema_context(empresa_a.schema_name):
        _padrao_da_empresa()

    previa = api.post(f"{NOTAS}previa/", corpo).json()["ibs_cbs"]

    assert previa == {
        "na_dps": True,
        "motivo": None,
        "origens": ORIGENS_EMPRESA,
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
        "nbs": "113011000",
        "cst": "200",
        "c_class_trib": "200003",
    }


def test_previa_diz_por_que_o_grupo_nao_vai(emissor_com_servico):
    api, corpo = emissor_com_servico  # a empresa não informa IBS/CBS

    resposta = api.post(f"{NOTAS}previa/", corpo).json()

    assert resposta["ibs_cbs"]["na_dps"] is False
    assert resposta["ibs_cbs"]["motivo"] == "A empresa não informa o IBS/CBS (parâmetros fiscais)."
    assert any("a empresa não informa IBS/CBS" in aviso for aviso in resposta["avisos"])


def test_previa_com_ajuste_pontual_mostra_a_nota_como_origem(emissor_com_servico, empresa_a):
    api, corpo = emissor_com_servico
    with schema_context(empresa_a.schema_name):
        _padrao_da_empresa()

    previa = api.post(
        f"{NOTAS}previa/",
        {**corpo, "ibs_cbs": {"codigo_indicador_operacao": OUTRO, "indicador_destinatario": 1}},
    ).json()["ibs_cbs"]

    assert (previa["codigo_indicador_operacao"], previa["indicador_destinatario"]) == (OUTRO, 1)
    assert previa["origens"] == {
        "informar": "nota",
        "codigo_indicador_operacao": "nota",
        "indicador_destinatario": "nota",
    }


def test_previa_recusa_ajuste_invalido_com_a_mensagem_no_campo(emissor_com_servico):
    api, corpo = emissor_com_servico

    resposta = api.post(
        f"{NOTAS}previa/", {**corpo, "ibs_cbs": {"codigo_indicador_operacao": "12"}}
    )

    assert resposta.status_code == 400
    assert resposta.json()["ibs_cbs"] == "O código do indicador da operação tem 6 dígitos."


def test_nota_criada_pela_api_herda_o_padrao_e_guarda_a_origem(emissor_com_servico, empresa_a):
    api, corpo = emissor_com_servico
    with schema_context(empresa_a.schema_name):
        _padrao_da_empresa()

    criada = api.post(NOTAS, corpo)

    assert criada.status_code == 201, criada.json()
    with schema_context(empresa_a.schema_name):
        grupo = Nfse.objects.get(pk=criada.json()["id"]).complementos["ibs_cbs"]
    assert grupo == {
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
        "origens": ORIGENS_EMPRESA,
    }
