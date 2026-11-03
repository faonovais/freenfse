"""IBS/CBS no modelo de NFS-e (issue #20, ADR 0007): o modelo herda da empresa e pode sobrescrever.

Prioridade, campo a campo (`informar`, `cIndOp`, `indDest`): nota/rascunho > modelo > empresa.
Campo vazio no modelo = herda o valor da empresa **de quando o rascunho é gerado** (nada é
copiado para o modelo). O serviço continua só com NBS, CST e cClassTrib.
"""

import datetime as dt
import importlib
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django_tenants.utils import schema_context
from lxml import etree

from agendamentos.models import ModeloNfse
from agendamentos.services import agenda, modelos
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from cadastros.models import Servico
from core.models import Empresa
from core.permissoes import Perfil
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse
from fiscal.tests.apoio import criar_cadastros_de_teste

pytestmark = pytest.mark.django_db
MODELOS = "/api/agendamentos/modelos/"
NOTAS = "/api/fiscal/notas/"
PADRAO, OUTRO, TERCEIRO = "010101", "020202", "030303"
NS = "{http://www.sped.fazenda.gov.br/nfse}"


def origens(nota):
    return nota.complementos["ibs_cbs"]["origens"]


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


@pytest.fixture
def servico_ibs(empresa_pronta):
    """Serviço com NBS, CST e cClassTrib: a classificação continua só no serviço."""
    criar_cadastros_de_teste()
    return Servico.objects.create(
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


def no_esquema():
    """Entra no schema da empresa de teste (após a API, a conexão volta ao schema público)."""
    return schema_context(Empresa.objects.exclude(schema_name="public").get().schema_name)


def empresa(informar=True, indicador=PADRAO, destinatario=0):
    """Define o padrão de IBS/CBS da empresa (os parâmetros fiscais)."""
    with no_esquema():
        ParametrosFiscais.objects.update(
            ibs_cbs_informar=informar,
            ibs_cbs_indicador_operacao=indicador,
            ibs_cbs_indicador_destinatario=destinatario,
        )


def hoje():
    # A API usa o relógio real (competência futura é recusada): as datas são sempre as de hoje.
    return timezone.localdate()


def gerar(modelo, responsavel):
    return modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=hoje())


def recarregar(objeto):
    with no_esquema():
        objeto.refresh_from_db()
    return objeto


def emitir(empresa_, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_)
    emissao.executar_emissao(empresa_, nota.pk)
    nota.refresh_from_db()
    return nota


# -- as três origens e a prioridade ---------------------------------------------------------


def test_modelo_que_herda_leva_tudo_da_empresa_e_o_rascunho_diz_isso(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(destinatario=1)
    modelo = criar_modelo(servico=servico_ibs)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == PADRAO
    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota) == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "empresa",
    }


def test_modelo_com_valor_proprio_vale_mais_que_a_empresa_so_nos_campos_dele(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(destinatario=0)
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO, ibs_cbs_indicador_destinatario=1
    )

    nota = gerar(modelo, responsavel)

    grupo = nota.complementos["ibs_cbs"]
    assert (grupo["codigo_indicador_operacao"], grupo["indicador_destinatario"]) == (OUTRO, 1)
    assert origens(nota) == {
        "informar": "modelo",
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "modelo",
    }


def test_so_o_destinatario_no_modelo_mantem_o_indicador_e_a_opcao_da_empresa(
    empresa_pronta, responsavel, servico_ibs
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_destinatario=1)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota) == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "modelo",
    }


def test_modelo_que_nao_informa_manda_o_rascunho_sem_o_grupo_e_diz_o_motivo(
    empresa_pronta, responsavel, servico_ibs
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_informar=False)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"] is None
    # A conferência do rascunho diz por quê, com a origem da decisão.
    preparo = servico_nfse.preparar(
        {"tomador": nota.tomador_ref_id, "servico": servico_ibs.pk, "competencia": nota.competencia,
         "valores": nota.valores, "ibs_cbs_modelo": nota.complementos["ibs_cbs_modelo"]},
        hoje=hoje(),
    )  # fmt: skip
    assert preparo.ibs_cbs_dps["motivo"] == "O modelo de NFS-e não informa o IBS/CBS."
    assert preparo.ibs_cbs_dps["origens"]["informar"] == "modelo"


def test_modelo_pode_mandar_informar_mesmo_com_a_opcao_da_empresa_desligada(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(informar=False)  # o indicador da empresa continua guardado
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_informar=True)

    nota = gerar(modelo, responsavel)

    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == PADRAO
    assert origens(nota)["informar"] == "modelo"
    assert origens(nota)["codigo_indicador_operacao"] == "empresa"


def test_modelo_que_manda_informar_sem_indicador_em_lugar_nenhum_nao_gera_rascunho(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(informar=False, indicador="")
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_informar=True)

    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        gerar(modelo, responsavel)

    assert "do modelo ou dos parâmetros fiscais da empresa" in erro.value.erros["ibs_cbs"]
    assert Nfse.objects.count() == 0
    # E o modelo ativo já avisa ao ser salvo, não só na hora de gerar.
    assert "ibs_cbs" in modelos.validar_modelo(modelo, hoje=hoje())


def test_modelo_manda_informar_e_o_servico_sem_classificacao_e_recusado(
    empresa_pronta, responsavel
):
    empresa()
    modelo = criar_modelo(ibs_cbs_informar=True)  # o serviço padrão dos testes não tem NBS/CST

    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        gerar(modelo, responsavel)

    assert "NBS, CST e classificação do IBS/CBS" in erro.value.erros["ibs_cbs"]


# -- herda de verdade: sem cópia ------------------------------------------------------------


def test_campo_vazio_herda_o_valor_da_empresa_de_agora_e_nada_e_copiado_para_o_modelo(
    empresa_pronta, responsavel, servico_ibs
):
    empresa(indicador=PADRAO)
    modelo = criar_modelo(servico=servico_ibs)
    primeira = gerar(modelo, responsavel)

    empresa(indicador=TERCEIRO, destinatario=1)  # a empresa muda DEPOIS de o modelo existir
    segunda = gerar(modelo, responsavel)

    assert primeira.complementos["ibs_cbs"]["codigo_indicador_operacao"] == PADRAO
    assert segunda.complementos["ibs_cbs"]["codigo_indicador_operacao"] == TERCEIRO
    assert segunda.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    modelo.refresh_from_db()  # o modelo continua vazio: herdar não é copiar
    assert modelo.padroes_de_ibs_cbs() == {
        "informar": None,
        "codigo_indicador_operacao": "",
        "indicador_destinatario": None,
    }


def test_mudar_a_empresa_altera_os_rascunhos_futuros_de_quem_herda_mas_nao_o_resto(
    empresa_pronta, responsavel, servico_ibs, sefin
):
    empresa(indicador=PADRAO)
    herda = criar_modelo(nome="Herda", servico=servico_ibs)
    proprio = criar_modelo(nome="Próprio", servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    emitida = emitir(empresa_pronta, gerar(herda, responsavel))  # nota já emitida
    rascunho_antigo = gerar(herda, responsavel)  # rascunho que já existia
    rascunho_proprio = gerar(proprio, responsavel)

    empresa(indicador=TERCEIRO)  # a empresa muda o padrão

    futuro_que_herda = gerar(herda, responsavel)
    futuro_proprio = gerar(proprio, responsavel)
    for nota in (emitida, rascunho_antigo, rascunho_proprio):
        nota.refresh_from_db()
    cind = lambda nota: nota.complementos["ibs_cbs"]["codigo_indicador_operacao"]  # noqa: E731
    assert cind(futuro_que_herda) == TERCEIRO  # rascunhos FUTUROS de quem herda mudam
    assert cind(futuro_proprio) == OUTRO  # o modelo com valor próprio não muda
    assert cind(rascunho_proprio) == OUTRO
    assert cind(rascunho_antigo) == PADRAO  # rascunho já criado é uma cópia: não muda sozinho
    assert cind(emitida) == PADRAO  # nota emitida nunca muda
    raiz = etree.fromstring(bytes(emitida.xml_dps))
    assert raiz.find(f".//{NS}IBSCBS").findtext(f"{NS}cIndOp") == PADRAO


def test_rascunho_guarda_o_que_o_modelo_definia_e_mudar_o_modelo_depois_nao_o_altera(
    empresa_pronta, responsavel, servico_ibs
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)

    ModeloNfse.objects.filter(pk=modelo.pk).update(ibs_cbs_indicador_operacao=TERCEIRO)
    nota.refresh_from_db()

    assert nota.complementos["ibs_cbs_modelo"] == {
        "informar": None,
        "codigo_indicador_operacao": OUTRO,
        "indicador_destinatario": None,
    }
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO


# -- o rascunho do agendamento continua ajustável -------------------------------------------


def test_rascunho_gerado_pelo_agendamento_leva_o_valor_efetivo(
    empresa_pronta, responsavel, servico_ibs
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    criar_agendamento(modelo, responsavel, agora=utc("2026-11-01T12:00"))

    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    nota = Nfse.objects.get()
    assert nota.complementos["ibs_cbs"]["codigo_indicador_operacao"] == OUTRO
    assert origens(nota)["codigo_indicador_operacao"] == "modelo"


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


def test_rascunho_do_agendamento_pode_ser_ajustado_antes_da_aprovacao(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)  # o mesmo caminho que o agendamento usa para gerar o rascunho

    ajustada = emissor.patch(
        f"{NOTAS}{nota.pk}/",
        corpo_da_nota(
            nota, ibs_cbs={"codigo_indicador_operacao": TERCEIRO, "indicador_destinatario": 1}
        ),
    )

    assert ajustada.status_code == 200, ajustada.json()
    recarregar(nota)
    grupo = nota.complementos["ibs_cbs"]
    assert (grupo["codigo_indicador_operacao"], grupo["indicador_destinatario"]) == (TERCEIRO, 1)
    assert grupo["origens"]["codigo_indicador_operacao"] == "nota"  # a nota passa à frente
    assert nota.complementos["ibs_cbs_nota"] == {
        "codigo_indicador_operacao": TERCEIRO,
        "indicador_destinatario": 1,
    }
    # O que o modelo definia segue guardado: dá para "voltar a herdar" no rascunho.
    assert nota.complementos["ibs_cbs_modelo"]["codigo_indicador_operacao"] == OUTRO


def test_voltar_a_herdar_no_rascunho_restaura_o_modelo_e_depois_a_empresa(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    empresa()
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
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_destinatario=1)
    nota = gerar(modelo, responsavel)

    emissor.patch(
        f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, valores={**nota.valores, "servico": "2000.00"})
    )

    recarregar(nota)
    assert nota.valor_servico == Decimal("2000.00")
    assert nota.complementos["ibs_cbs"]["indicador_destinatario"] == 1
    assert origens(nota)["indicador_destinatario"] == "modelo"


def test_a_nota_pode_dispensar_o_grupo_que_o_modelo_manda_informar(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    empresa()
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_informar=True)
    nota = gerar(modelo, responsavel)
    assert nota.complementos["ibs_cbs"] is not None

    emissor.patch(f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, ibs_cbs={"informar": False}))

    recarregar(nota)
    assert nota.complementos["ibs_cbs"] is None
    assert nota.complementos["ibs_cbs_nota"] == {"informar": False}


# -- a prévia mostra o valor e a origem -----------------------------------------------------


def test_previa_do_rascunho_mostra_cada_campo_com_a_origem(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    empresa(indicador=PADRAO, destinatario=0)
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_operacao=OUTRO)
    nota = gerar(modelo, responsavel)

    previa = emissor.post(
        f"{NOTAS}previa/",
        {**corpo_da_nota(nota), "rascunho": nota.pk, "ibs_cbs": {"indicador_destinatario": 1}},
    ).json()["ibs_cbs"]

    assert previa["na_dps"] is True
    assert (previa["codigo_indicador_operacao"], previa["indicador_destinatario"]) == (OUTRO, 1)
    assert previa["origens"] == {
        "informar": "modelo",
        "codigo_indicador_operacao": "modelo",  # do modelo do rascunho
        "indicador_destinatario": "nota",  # ajustado na conferência
    }


def test_previa_de_nota_nova_sem_modelo_mostra_a_empresa_como_origem(
    empresa_pronta, servico_ibs, emissor
):
    empresa()
    tomador, _ = criar_cadastros_de_teste()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico_ibs.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "100.00"},
    }

    previa = emissor.post(f"{NOTAS}previa/", corpo).json()["ibs_cbs"]

    assert previa["origens"] == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "empresa",
    }


# -- a API do modelo: valor próprio, herdado, efetivo e "voltar a herdar" -------------------


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


def test_api_do_modelo_mostra_o_proprio_o_herdado_da_empresa_e_o_efetivo_com_a_origem(
    empresa_pronta, emissor, modelo_api
):
    empresa(indicador=PADRAO, destinatario=0)

    corpo = emissor.get(f"{MODELOS}{modelo_api['id']}/").json()

    assert corpo["ibs_cbs_informar"] is None  # o modelo não define: herda
    assert corpo["ibs_cbs_indicador_operacao"] == ""
    assert corpo["ibs_cbs_indicador_destinatario"] is None
    assert corpo["ibs_cbs_herdado"] == {
        "informar": True,
        "codigo_indicador_operacao": PADRAO,
        "indicador_destinatario": 0,
    }
    assert corpo["ibs_cbs_efetivo"]["codigo_indicador_operacao"] == PADRAO
    assert corpo["ibs_cbs_efetivo"]["origens"] == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "empresa",
    }


def test_api_sobrescrever_e_voltar_a_herdar_campo_a_campo(empresa_pronta, emissor, modelo_api):
    empresa(indicador=PADRAO)
    url = f"{MODELOS}{modelo_api['id']}/"

    sobrescrito = emissor.patch(
        url,
        {
            "ibs_cbs_informar": True,
            "ibs_cbs_indicador_operacao": "020.202",  # só os dígitos valem
            "ibs_cbs_indicador_destinatario": 1,
        },
    ).json()
    assert sobrescrito["ibs_cbs_indicador_operacao"] == OUTRO
    assert sobrescrito["ibs_cbs_efetivo"]["origens"] == {
        "informar": "modelo",
        "codigo_indicador_operacao": "modelo",
        "indicador_destinatario": "modelo",
    }

    # "Voltar a herdar": nulo/vazio por campo. Um de cada vez, para provar que são independentes.
    sem_indicador = emissor.patch(url, {"ibs_cbs_indicador_operacao": ""}).json()
    assert sem_indicador["ibs_cbs_efetivo"]["origens"]["codigo_indicador_operacao"] == "empresa"
    assert sem_indicador["ibs_cbs_efetivo"]["origens"]["indicador_destinatario"] == "modelo"
    sem_destinatario = emissor.patch(url, {"ibs_cbs_indicador_destinatario": None}).json()
    assert sem_destinatario["ibs_cbs_efetivo"]["origens"]["indicador_destinatario"] == "empresa"
    sem_opcao = emissor.patch(url, {"ibs_cbs_informar": None}).json()
    assert sem_opcao["ibs_cbs_efetivo"]["origens"] == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "empresa",
    }
    with no_esquema():
        modelo = ModeloNfse.objects.get(pk=modelo_api["id"])
    assert modelo.padroes_de_ibs_cbs() == {
        "informar": None,
        "codigo_indicador_operacao": "",
        "indicador_destinatario": None,
    }


def test_api_o_efetivo_do_modelo_acompanha_a_empresa_na_hora(empresa_pronta, emissor, modelo_api):
    url = f"{MODELOS}{modelo_api['id']}/"
    empresa(indicador=PADRAO)
    antes = emissor.get(url).json()["ibs_cbs_efetivo"]["codigo_indicador_operacao"]

    empresa(indicador=TERCEIRO)
    depois = emissor.get(url).json()["ibs_cbs_efetivo"]["codigo_indicador_operacao"]

    assert (antes, depois) == (PADRAO, TERCEIRO)


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


def test_api_opcoes_traz_o_padrao_de_ibs_cbs_da_empresa_de_agora(empresa_pronta, emissor):
    empresa(informar=True, indicador=TERCEIRO, destinatario=1)

    opcoes = emissor.get("/api/agendamentos/opcoes/").json()

    assert opcoes["ibs_cbs_empresa"] == {
        "informar": True,
        "codigo_indicador_operacao": TERCEIRO,
        "indicador_destinatario": 1,
    }


def test_api_conferir_o_modelo_mostra_o_ibs_cbs_com_a_origem_de_cada_campo(
    empresa_pronta, emissor, modelo_api
):
    empresa(indicador=PADRAO, destinatario=0)
    emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"ibs_cbs_indicador_destinatario": 1})

    conferencia = emissor.post(f"{MODELOS}{modelo_api['id']}/previa/").json()

    assert conferencia["ok"] is True
    ibs = conferencia["ibs_cbs"]
    assert (ibs["codigo_indicador_operacao"], ibs["indicador_destinatario"]) == (PADRAO, 1)
    assert ibs["origens"] == {
        "informar": "empresa",
        "codigo_indicador_operacao": "empresa",
        "indicador_destinatario": "modelo",
    }


# -- migração: modelos existentes ficam "herda da empresa" ----------------------------------


def test_modelos_que_ja_existiam_ficam_herdando_da_empresa_depois_da_migracao(empresa_a):
    antes = [("agendamentos", "0001_fase_5")]
    depois = [("agendamentos", "0002_ibs_cbs_no_modelo")]
    migracao = importlib.import_module("agendamentos.migrations.0002_ibs_cbs_no_modelo").Migration
    assert {type(op).__name__ for op in migracao.operations} == {"AddField"}  # só acrescenta

    with schema_context(empresa_a.schema_name):
        executor = MigrationExecutor(connection)
        executor.migrate(antes)
        antigo = MigrationExecutor(connection).loader.project_state(antes).apps
        existente = antigo.get_model("agendamentos", "ModeloNfse").objects.create(
            nome="Modelo de antes", valores={"servico": "100.00"}
        )

        # Restrições diferidas da linha inserida precisam valer antes do ALTER TABLE da migração.
        connection.cursor().execute("SET CONSTRAINTS ALL IMMEDIATE")
        executor = MigrationExecutor(connection)
        executor.migrate(depois)

        modelo = ModeloNfse.objects.get(pk=existente.pk)
        assert modelo.nome == "Modelo de antes" and modelo.valores == {"servico": "100.00"}
        assert modelo.padroes_de_ibs_cbs() == {
            "informar": None,
            "codigo_indicador_operacao": "",
            "indicador_destinatario": None,
        }
