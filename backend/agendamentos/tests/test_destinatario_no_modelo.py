"""Destinatário no modelo de NFS-e (issue #33, ADR 0011).

O modelo pode escolher a pessoa (do cadastro) que as notas trazem no grupo `dest` quando o
destinatário é outra pessoa (`indDest = 1`). Vazio = o modelo não define e cada nota escolhe.
Prioridade: nota > modelo.
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
from conftest import cnpj_de_teste
from core.models import Empresa
from core.permissoes import Perfil
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.tests.apoio import criar_cadastros_de_teste, criar_destinatario_de_teste

pytestmark = pytest.mark.django_db
MODELOS = "/api/agendamentos/modelos/"
NOTAS = "/api/fiscal/notas/"
DO_SERVICO, EXIGE = "100301", "000001"


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A tabela de municípios valida o município do emissor."""


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


@pytest.fixture
def emissor(api_de, empresa_pronta):
    return api_de(empresa_pronta, Perfil.EMISSOR)


@pytest.fixture
def servico_ibs(empresa_pronta):
    """Serviço cuja classificação EXIGE o grupo de IBS/CBS."""
    criar_cadastros_de_teste()
    return Servico.objects.create(
        nome="Serviço com grupo",
        descricao="Análise e desenvolvimento de sistemas.",
        codigo_tributacao_nacional="010101",
        codigo_tributacao_municipal="002",
        nbs="115021000",
        aliquota_iss=Decimal("2.00"),
        vigencia_inicio=dt.date(2026, 1, 1),
        cst_ibs_cbs="000",
        c_class_trib=EXIGE,
        codigo_indicador_operacao=DO_SERVICO,
    )


def no_esquema():
    """Entra no schema da empresa de teste (após a API, a conexão volta ao schema público)."""
    return schema_context(Empresa.objects.exclude(schema_name="public").get().schema_name)


def hoje():
    return timezone.localdate()


def gerar(modelo, responsavel):
    return modelos.gerar_rascunho(modelo, usuario=responsavel, data_execucao=hoje())


def recarregar(objeto):
    with no_esquema():
        objeto.refresh_from_db()
    return objeto


def corpo_da_nota(nota, **extra):
    return {
        "tomador": nota.tomador_ref_id,
        "servico": nota.servico_ref_id,
        "competencia": nota.competencia.isoformat(),
        "valores": nota.valores,
        **extra,
    }


# -- o modelo define o destinatário ---------------------------------------------------------


def test_modelo_com_destinatario_leva_a_pessoa_para_o_rascunho_quando_e_outra_pessoa(
    empresa_pronta, responsavel, servico_ibs
):
    destinatario = criar_destinatario_de_teste()
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=destinatario
    )

    nota = gerar(modelo, responsavel)

    info = nota.complementos["destinatario"]
    assert info["pessoa"] == destinatario.pk and info["origem"] == "modelo"
    assert info["dados"]["nome"] == destinatario.nome
    assert nota.complementos["destinatario_modelo"] == destinatario.pk
    assert nota.complementos["destinatario_nota"] is None


def test_modelo_com_o_proprio_tomador_nao_leva_o_destinatario(
    empresa_pronta, responsavel, servico_ibs
):
    modelo = criar_modelo(
        servico=servico_ibs,
        ibs_cbs_indicador_destinatario=0,
        destinatario=criar_destinatario_de_teste(),
    )

    nota = gerar(modelo, responsavel)

    assert nota.complementos["destinatario"] is None
    assert nota.complementos["destinatario_modelo"] == modelo.destinatario_id  # segue guardado


def test_modelo_sem_destinatario_e_com_outra_pessoa_nao_gera_rascunho(
    empresa_pronta, responsavel, servico_ibs
):
    modelo = criar_modelo(servico=servico_ibs, ibs_cbs_indicador_destinatario=1)

    problemas = modelos.erros_de_preparo(modelo, hoje=hoje())

    assert "Escolha o destinatário" in problemas["destinatario"]


def test_rascunho_do_agendamento_leva_o_destinatario_do_modelo(
    empresa_pronta, responsavel, servico_ibs
):
    destinatario = criar_destinatario_de_teste()
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=destinatario
    )
    criar_agendamento(modelo, responsavel, agora=utc("2026-11-01T12:00"))

    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    nota = Nfse.objects.get()
    assert nota.complementos["destinatario"]["pessoa"] == destinatario.pk
    assert nota.complementos["destinatario"]["origem"] == "modelo"


# -- herda de verdade, a nota pode trocar -----------------------------------------------------


def test_rascunho_guarda_a_cópia_e_mudar_o_modelo_ou_a_pessoa_depois_nao_o_altera(
    empresa_pronta, responsavel, servico_ibs
):
    destinatario = criar_destinatario_de_teste()
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=destinatario
    )
    nota = gerar(modelo, responsavel)

    outra = criar_destinatario_de_teste(documento=cnpj_de_teste("054239600009"), nome="OUTRA")
    with no_esquema():
        ModeloNfse.objects.filter(pk=modelo.pk).update(destinatario=outra)
        destinatario.nome = "NOME ALTERADO"
        destinatario.save()

    recarregar(nota)
    assert nota.complementos["destinatario"]["pessoa"] == destinatario.pk
    assert nota.complementos["destinatario"]["dados"]["nome"] == "DESTINATARIO FICTICIO LTDA"


def test_a_nota_troca_o_destinatario_do_modelo_e_volta_a_herdar(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    do_modelo = criar_destinatario_de_teste()
    da_nota = criar_destinatario_de_teste(documento=cnpj_de_teste("054239600008"), nome="DA NOTA")
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=do_modelo
    )
    nota = gerar(modelo, responsavel)
    url = f"{NOTAS}{nota.pk}/"

    trocada = emissor.patch(url, corpo_da_nota(nota, destinatario=da_nota.pk))
    assert trocada.status_code == 200, trocada.json()
    recarregar(nota)
    assert nota.complementos["destinatario"]["pessoa"] == da_nota.pk
    assert nota.complementos["destinatario"]["origem"] == "nota"
    assert nota.complementos["destinatario_modelo"] == do_modelo.pk

    emissor.patch(url, corpo_da_nota(nota, destinatario=None))  # voltar a herdar
    recarregar(nota)
    assert nota.complementos["destinatario"]["pessoa"] == do_modelo.pk
    assert nota.complementos["destinatario"]["origem"] == "modelo"
    assert nota.complementos["destinatario_nota"] is None


def test_editar_o_rascunho_sem_mexer_no_destinatario_mantem_o_do_modelo(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    destinatario = criar_destinatario_de_teste()
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=destinatario
    )
    nota = gerar(modelo, responsavel)

    emissor.patch(
        f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, valores={**nota.valores, "servico": "2000.00"})
    )

    recarregar(nota)
    assert nota.valor_servico == Decimal("2000.00")
    assert nota.complementos["destinatario"]["origem"] == "modelo"


def test_previa_do_rascunho_corrigido_mostra_o_destinatario_do_modelo(
    empresa_pronta, responsavel, servico_ibs, emissor
):
    destinatario = criar_destinatario_de_teste()
    modelo = criar_modelo(
        servico=servico_ibs, ibs_cbs_indicador_destinatario=1, destinatario=destinatario
    )
    nota = gerar(modelo, responsavel)

    previa = emissor.post(f"{NOTAS}previa/", corpo_da_nota(nota, rascunho=nota.pk)).json()

    assert previa["complementos"]["destinatario"]["origem"] == "modelo"
    assert previa["complementos"]["destinatario"]["pessoa"] == destinatario.pk


# -- a API do modelo ---------------------------------------------------------------------------


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


def test_api_do_modelo_mostra_o_destinatario_vazio_por_padrao(emissor, modelo_api):
    corpo = emissor.get(f"{MODELOS}{modelo_api['id']}/").json()

    assert corpo["destinatario"] is None and corpo["destinatario_nome"] == ""


def test_api_escolher_e_limpar_o_destinatario_do_modelo(emissor, modelo_api):
    with no_esquema():
        destinatario = criar_destinatario_de_teste()
    url = f"{MODELOS}{modelo_api['id']}/"

    escolhido = emissor.patch(url, {"destinatario": destinatario.pk}).json()
    assert escolhido["destinatario"] == destinatario.pk
    assert escolhido["destinatario_nome"] == destinatario.nome

    limpo = emissor.patch(url, {"destinatario": None}).json()
    assert limpo["destinatario"] is None and limpo["destinatario_nome"] == ""


def test_api_recusa_destinatario_que_nao_existe(emissor, modelo_api):
    resposta = emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"destinatario": 99999})

    assert resposta.status_code == 400
    assert "Destinatário não encontrado" in str(resposta.json()["destinatario"])


def test_api_conferir_o_modelo_mostra_o_destinatario_escolhido(emissor, modelo_api):
    with no_esquema():
        ParametrosFiscais.objects.update(ibs_cbs_indicador_destinatario=1)
        destinatario = criar_destinatario_de_teste()
    emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"destinatario": destinatario.pk})

    conferencia = emissor.post(f"{MODELOS}{modelo_api['id']}/previa/").json()

    assert conferencia["ok"] is True
    assert conferencia["ibs_cbs"]["indicador_destinatario"] == 1
