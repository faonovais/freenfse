"""IBS/CBS no modelo de NFS-e (issue #29, ADR 0010): o modelo só ajusta o que herda.

Se o grupo vai é decidido pela classificação do serviço. O modelo pode ajustar, para exceções, o
`cIndOp` (vazio = herda o do **serviço**) e o `indDest` (vazio = herda o da **empresa**), sempre
**de quando o rascunho é gerado**: nada é copiado para o modelo. Prioridade: nota > modelo > serviço
(cIndOp) e nota > modelo > empresa (indDest).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from agendamentos.models import ModeloNfse
from agendamentos.services import agenda, modelos
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from cadastros.models import Servico
from core.models import Empresa
from core.permissoes import Perfil
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.tests.apoio import criar_cadastros_de_teste, criar_destinatario_de_teste

pytestmark = pytest.mark.django_db
MODELOS = "/api/agendamentos/modelos/"
NOTAS = "/api/fiscal/notas/"
DO_SERVICO, OUTRO, TERCEIRO = "100301", "050101", "050102"  # Anexo VIII: item 01.01 + NBS 1.1502.10
EXIGE, NAO_EXIGE = "000001", "410009"


def origens(nota):
    return nota.complementos["ibs_cbs"]["origens"]


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


def _servico(municipal, **campos):
    base = {
        "nome": f"Serviço {municipal}",
        "descricao": "Análise e desenvolvimento de sistemas.",
        "codigo_tributacao_nacional": "010101",
        "codigo_tributacao_municipal": municipal,
        "nbs": "115021000",
        "aliquota_iss": Decimal("2.00"),
        "vigencia_inicio": dt.date(2026, 1, 1),
    }
    return Servico.objects.create(**{**base, **campos})


@pytest.fixture
def servico_ibs(empresa_pronta):
    """Serviço cuja classificação EXIGE o grupo de IBS/CBS, com o cIndOp do Anexo VIII."""
    criar_cadastros_de_teste()
    return _servico(
        "002", cst_ibs_cbs="000", c_class_trib=EXIGE, codigo_indicador_operacao=DO_SERVICO
    )


def no_esquema():
    """Entra no schema da empresa de teste (após a API, a conexão volta ao schema público)."""
    return schema_context(Empresa.objects.exclude(schema_name="public").get().schema_name)


def empresa(destinatario=0):
    """Define o padrão de destinatário da empresa (a única coisa de IBS/CBS que ela tem)."""
    with no_esquema():
        ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=destinatario)


def servico_muda(servico, **campos):
    with no_esquema():
        for campo, valor in campos.items():
            setattr(servico, campo, valor)
        servico.save()


def hoje():
    # A API usa o relógio real (competência futura é recusada): as datas são sempre as de hoje.
    return timezone.localdate()


def gerar(modelo, responsavel):
    return modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=hoje())


def recarregar(objeto):
    with no_esquema():
        objeto.refresh_from_db()
    return objeto


# -- as origens e a prioridade --------------------------------------------------------------


def test_modelo_que_herda_leva_o_cindop_do_servico_e_o_destinatario_da_empresa(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(destinatario=1)
    modelo = criar_modelo(servico=servico_ibs, destinatario=criar_destinatario_de_teste())

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == DO_SERVICO
    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota) == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "empresa",
    }


def test_modelo_com_valor_proprio_vale_mais_que_o_servico_so_nos_campos_dele(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(destinatario=0)
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO
    assert origens(nota) == {
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "empresa",
    }


def test_so_o_destinatario_no_modelo_mantem_o_cindop_do_servico(
    empresa_pronta, responsavel, servico_ibs
):
    empresa()
    modelo = criar_modelo(
        servico=servico_ibs,
        ibs_cbs_indicador_destinatario=1,
        destinatario=criar_destinatario_de_teste(),
    )

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == DO_SERVICO
    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota) == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "modelo",
    }


def test_modelo_de_servico_que_nao_exige_o_grupo_gera_rascunho_sem_grupo(
    empresa_pronta, responsavel
):
    criar_cadastros_de_teste()
    servico = _servico("003", cst_ibs_cbs="410", c_class_trib=NAO_EXIGE)
    modelo = criar_modelo(servico=servico, ibs_cbs_indicador_operacao=OUTRO)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"] is None  # o ajuste do modelo não vale sem tributação


def test_servico_que_exige_o_grupo_sem_cindop_em_lugar_nenhum_nao_gera_rascunho(
    empresa_pronta, responsavel, servico_ibs
):
    servico_muda(servico_ibs, codigo_indicador_operacao="")
    modelo = criar_modelo(servico=servico_ibs)

    problemas = modelos.erros_de_preparo(modelo, hoje=hoje())

    assert "E0860" in problemas["ibs_cbs"]


def test_o_ajuste_do_modelo_supre_o_cindop_que_o_servico_nao_tem(
    empresa_pronta, responsavel, servico_ibs
):
    servico_muda(servico_ibs, codigo_indicador_operacao="")
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO


# -- herda de verdade: sem cópia ------------------------------------------------------------


def test_campo_vazio_herda_o_valor_de_agora_e_nada_e_copiado_para_o_modelo(
    empresa_pronta, responsavel, servico_ibs
):
    modelo = criar_modelo(servico=servico_ibs)

    servico_muda(servico_ibs, codigo_indicador_operacao=DO_SERVICO)
    antes = gerar(modelo, responsavel)
    servico_muda(servico_ibs, codigo_indicador_operacao=TERCEIRO)
    depois = gerar(modelo, responsavel)

    assert antes.complementos["ibs_cbs"]["codigo_indicador_operacao"] == DO_SERVICO
    assert depois.complementos["ibs_cbs"]["codigo_indicador_operacao"] == TERCEIRO
    assert recarregar(modelo).padroes_de_ibs_cbs() == {
        "codigo_indicador_operacao": "",
        "indicador_destinatario": None,
    }


def test_mudar_a_empresa_altera_os_rascunhos_futuros_de_quem_herda_mas_nao_o_resto(
    empresa_pronta, responsavel, servico_ibs
):
    destinatario = criar_destinatario_de_teste()
    herda = criar_modelo(nome="Herda", servico=servico_ibs, destinatario=destinatario)
    proprio = criar_modelo(
        nome="Próprio",
        servico=servico_ibs,
        ibs_cbs_indicador_destinatario=1,
        destinatario=destinatario,
    )

    empresa(destinatario=0)
    antes = gerar(herda, responsavel)
    empresa(destinatario=1)
    herdado_depois = gerar(herda, responsavel)
    proprio_depois = gerar(proprio, responsavel)

    assert antes.complementos["ibs_cbs"]["indicador_destinatario"] == 0  # o rascunho já nascido
    assert herdado_depois.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert proprio_depois.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(herdado_depois)["indicador_destinatario"] == "empresa"
    assert origens(proprio_depois)["indicador_destinatario"] == "modelo"


def test_rascunho_guarda_o_que_o_modelo_definia_e_mudar_o_modelo_depois_nao_o_altera(
    empresa_pronta, responsavel, servico_ibs
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)

    with no_esquema():
        ModeloNfse.objects.filter(pk=modelo.pk).update(ibs_cbs_indicador_operacao=TERCEIRO)

    recarregar(nota)
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO
    assert nota.complementos["ibs_cbs_modelo"]["codigo_indicador_operacao"] == OUTRO


# -- o rascunho do agendamento continua ajustável ---------------------------------------------


@pytest.fixture
def emissor(api_de, empresa_pronta):
    return api_de(empresa_pronta, Perfil.EMISSOR)


def corpo_da_nota(nota, **extra):
    """O corpo que a tela de correção do rascunho envia."""
    return {
        "tomador": nota.tomador_ref_id,
        "servico": nota.servico_ref_id,
        "competencia": nota.competencia.isoformat(),
        "valores": nota.valores,
        **extra,
    }


def test_rascunho_gerado_pelo_agendamento_leva_o_valor_efetivo(
    empresa_pronta, responsavel, servico_ibs
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    criar_agendamento(modelo, responsavel, agora=utc("2026-11-01T12:00"))

    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    nota = Nfse.objects.get()
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO
    assert origens(nota)["codigo_indicador_operacao"] == "modelo"


def test_rascunho_do_agendamento_pode_ser_ajustado_antes_da_aprovacao(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)
    destinatario = criar_destinatario_de_teste()

    ajustada = emissor.patch(
        f"{NOTAS}{nota.pk}/",
        corpo_da_nota(
            nota,
            ibs_cbs={"codigo_indicador_operacao": TERCEIRO, "indicador_destinatario": 1},
            destinatario=destinatario.pk,
        ),
    )

    assert ajustada.status_code == 200, ajustada.json()
    recarregar(nota)
    grupo = nota.complementos["ibs_cbs"]
    assert (grupo["codigo_indicador_operacao"], grupo["indicador_destinatario"]) == (TERCEIRO, 1)
    assert grupo["origens"]["codigo_indicador_operacao"] == "nota"  # a nota passa à frente
    assert nota.complementos["ibs_cbs_modelo"]["codigo_indicador_operacao"] == OUTRO


def test_voltar_a_herdar_no_rascunho_restaura_o_modelo(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)
    emissor.patch(
        f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, ibs_cbs={"codigo_indicador_operacao": TERCEIRO})
    )

    emissor.patch(f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, ibs_cbs=None))  # sem ajuste da nota

    recarregar(nota)
    assert nota.complementos["ibs_cbs_nota"] is None
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO
    assert origens(nota)["codigo_indicador_operacao"] == "modelo"


def test_editar_o_rascunho_sem_mexer_no_ibs_cbs_mantem_o_que_o_modelo_definia(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    modelo = criar_modelo(
        servico=servico_ibs,
        ibs_cbs_indicador_destinatario=1,
        destinatario=criar_destinatario_de_teste(),
    )
    nota = gerar(modelo, responsavel)

    emissor.patch(
        f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, valores={**nota.valores, "servico": "2000.00"})
    )

    recarregar(nota)
    assert nota.valor_servico == Decimal("2000.00")
    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota)["indicador_destinatario"] == "modelo"


# -- a prévia mostra o valor e a origem -----------------------------------------------------


def test_previa_do_rascunho_mostra_cada_campo_com_a_origem(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)

    previa = emissor.post(f"{NOTAS}previa/", corpo_da_nota(nota, rascunho=nota.pk)).json()

    ibs = previa["ibs_cbs"]
    assert (ibs["na_dps"], ibs["codigo_indicador_operacao"]) == (True, OUTRO)
    assert ibs["origens"] == {
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "empresa",
    }


def test_previa_de_nota_nova_sem_modelo_mostra_o_servico_como_origem(
    empresa_pronta, servico_ibs, emissor
):
    tomador, _ = criar_cadastros_de_teste()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico_ibs.pk,
        "competencia": hoje().isoformat(),
        "valores": {"servico": "100.00"},
    }

    ibs = emissor.post(f"{NOTAS}previa/", corpo).json()["ibs_cbs"]

    assert ibs["origens"]["codigo_indicador_operacao"] == "servico"


# -- a API do modelo: valor próprio, herdado, efetivo e "voltar a herdar" ---------------------


@pytest.fixture
def modelo_api(empresa_pronta, emissor, servico_ibs):
    tomador, _ = criar_cadastros_de_teste()
    resposta = emissor.post(
        MODELOS,
        {
            "nome": "Mensalidade",
            "ativo": True,
            "tomador": tomador.pk,
            "servico": servico_ibs.pk,
            "valores": {"servico": "1500.00"},
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def test_api_do_modelo_mostra_o_proprio_o_herdado_e_o_efetivo_com_a_origem(
    empresa_pronta, emissor, modelo_api
):
    empresa(destinatario=0)

    corpo = emissor.get(f"{MODELOS}{modelo_api['id']}/").json()

    assert "ibs_cbs_informar" not in corpo
    assert corpo["ibs_cbs_indicador_operacao"] == ""
    assert corpo["ibs_cbs_indicador_destinatario"] is None
    assert corpo["ibs_cbs_herdado"] == {
        "indicador_destinatario": 0,
        "codigo_indicador_operacao": DO_SERVICO,
    }
    assert corpo["ibs_cbs_efetivo"]["codigo_indicador_operacao"] == DO_SERVICO
    assert corpo["ibs_cbs_efetivo"]["origens"] == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "empresa",
    }


def test_api_sobrescrever_e_voltar_a_herdar_campo_a_campo(empresa_pronta, emissor, modelo_api):
    url = f"{MODELOS}{modelo_api['id']}/"

    sobrescrito = emissor.patch(
        url, {"ibs_cbs_indicador_operacao": "050.101", "ibs_cbs_indicador_destinatario": 1}
    ).json()  # só os dígitos valem
    assert sobrescrito["ibs_cbs_indicador_operacao"] == OUTRO
    assert sobrescrito["ibs_cbs_efetivo"]["origens"] == {
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "modelo",
    }

    # "Voltar a herdar": nulo/vazio por campo. Um de cada vez, para provar que são independentes.
    sem_indicador = emissor.patch(url, {"ibs_cbs_indicador_operacao": ""}).json()
    assert sem_indicador["ibs_cbs_efetivo"]["origens"] == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "modelo",
    }
    sem_destinatario = emissor.patch(url, {"ibs_cbs_indicador_destinatario": None}).json()
    assert sem_destinatario["ibs_cbs_efetivo"]["origens"]["indicador_destinatario"] == "empresa"
    with no_esquema():
        modelo = ModeloNfse.objects.get(pk=modelo_api["id"])
    assert modelo.padroes_de_ibs_cbs() == {
        "codigo_indicador_operacao": "",
        "indicador_destinatario": None,
    }


def test_api_o_efetivo_do_modelo_acompanha_o_servico_na_hora(
    empresa_pronta, emissor, modelo_api, servico_ibs
):
    url = f"{MODELOS}{modelo_api['id']}/"
    antes = emissor.get(url).json()["ibs_cbs_efetivo"]["codigo_indicador_operacao"]

    servico_muda(servico_ibs, codigo_indicador_operacao=TERCEIRO)
    depois = emissor.get(url).json()["ibs_cbs_efetivo"]["codigo_indicador_operacao"]

    assert (antes, depois) == (DO_SERVICO, TERCEIRO)


def test_api_ignora_o_campo_informar_de_clientes_defasados(empresa_pronta, emissor, modelo_api):
    resposta = emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"ibs_cbs_informar": False})

    assert resposta.status_code == 200, resposta.json()
    assert "ibs_cbs_informar" not in resposta.json()


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("ibs_cbs_indicador_operacao", "12345", "6 dígitos"),
        ("ibs_cbs_indicador_operacao", "1234567", "6 dígitos"),
        ("ibs_cbs_indicador_destinatario", 2, ""),
    ],
)
def test_api_recusa_indicador_e_destinatario_invalidos_no_modelo(
    empresa_pronta, emissor, modelo_api, campo, valor, trecho
):
    resposta = emissor.patch(f"{MODELOS}{modelo_api['id']}/", {campo: valor})

    assert resposta.status_code == 400
    assert trecho in str(resposta.json()[campo])


def test_api_opcoes_traz_so_o_destinatario_da_empresa_de_agora(empresa_pronta, emissor):
    empresa(destinatario=1)

    opcoes = emissor.get("/api/agendamentos/opcoes/").json()

    assert opcoes["ibs_cbs_empresa"] == {"indicador_destinatario": 1}


def test_api_conferir_o_modelo_mostra_o_ibs_cbs_com_a_origem_de_cada_campo(
    empresa_pronta, emissor, modelo_api
):
    with no_esquema():
        destinatario = criar_destinatario_de_teste()
    emissor.patch(
        f"{MODELOS}{modelo_api['id']}/",
        {"ibs_cbs_indicador_destinatario": 1, "destinatario": destinatario.pk},
    )

    conferencia = emissor.post(f"{MODELOS}{modelo_api['id']}/previa/").json()

    assert conferencia["ok"] is True
    ibs = conferencia["ibs_cbs"]
    assert (ibs["codigo_indicador_operacao"], ibs["indicador_destinatario"]) == (DO_SERVICO, 1)
    assert ibs["origens"] == {
        "codigo_indicador_operacao": "servico",
        "indicador_destinatario": "modelo",
    }
