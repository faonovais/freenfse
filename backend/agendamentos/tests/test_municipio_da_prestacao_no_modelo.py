"""Município da prestação no modelo de NFS-e (issue #29, ADR 0010).

O modelo pode definir o município da prestação (código IBGE). Vazio = herda o padrão, que é o
município do emissor **de quando o rascunho é gerado**: nada é copiado para o modelo. Prioridade:
nota > modelo > emissor. A nota pode sobrescrever o do modelo e "voltar a herdar".
"""

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from agendamentos.models import ModeloNfse
from agendamentos.services import agenda, modelos
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from core.models import Empresa
from core.permissoes import Perfil
from fiscal.models import Nfse, ParametrosFiscais

pytestmark = pytest.mark.django_db
MODELOS = "/api/agendamentos/modelos/"
NOTAS = "/api/fiscal/notas/"
EMISSOR, SAO_PAULO, PALMAS, BALSAS = "2903201", "3550308", "1721000", "2101400"


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A tabela de municípios é o que valida o código."""


@pytest.fixture
def responsavel(empresa_pronta):
    return criar_usuario("resp@exemplo.test", empresa_pronta)


@pytest.fixture
def emissor(api_de, empresa_pronta):
    return api_de(empresa_pronta, Perfil.EMISSOR)


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


def local(nota):
    return nota.complementos["local_prestacao"]


def corpo_da_nota(nota, **extra):
    """O corpo que a tela de correção do rascunho envia."""
    return {
        "tomador": nota.tomador_ref_id,
        "servico": nota.servico_ref_id,
        "competencia": nota.competencia.isoformat(),
        "valores": nota.valores,
        **extra,
    }


# -- as origens e a prioridade --------------------------------------------------------------


def test_modelo_sem_municipio_herda_o_do_emissor(empresa_pronta, responsavel):
    modelo = criar_modelo()

    nota = gerar(modelo, responsavel)

    assert local(nota) == {"codigo": EMISSOR, "origem": "emissor"}


def test_modelo_com_municipio_leva_o_dele_para_o_rascunho(empresa_pronta, responsavel):
    modelo = criar_modelo(codigo_municipio_prestacao=SAO_PAULO)

    nota = gerar(modelo, responsavel)

    assert local(nota) == {"codigo": SAO_PAULO, "origem": "modelo"}
    assert nota.complementos["municipio_prestacao_modelo"] == SAO_PAULO
    assert nota.complementos["municipio_prestacao_nota"] is None


def test_rascunho_do_agendamento_leva_o_municipio_do_modelo(empresa_pronta, responsavel):
    modelo = criar_modelo(codigo_municipio_prestacao=PALMAS)
    criar_agendamento(modelo, responsavel, agora=utc("2026-11-01T12:00"))

    agenda.despachar(utc("2026-11-05T11:01"), empresa=empresa_pronta)

    nota = Nfse.objects.get()
    assert local(nota) == {"codigo": PALMAS, "origem": "modelo"}


# -- herda de verdade: sem cópia ------------------------------------------------------------


def test_mudar_o_emissor_altera_os_rascunhos_futuros_de_quem_herda_mas_nao_o_resto(
    empresa_pronta, responsavel
):
    herda = criar_modelo(nome="Herda")
    proprio = criar_modelo(nome="Próprio", codigo_municipio_prestacao=PALMAS)

    antes = gerar(herda, responsavel)
    with no_esquema():
        ParametrosFiscais.objects.update(codigo_municipio_emissor=BALSAS)
    herdado_depois = gerar(herda, responsavel)
    proprio_depois = gerar(proprio, responsavel)

    assert local(antes)["codigo"] == EMISSOR  # o rascunho já nascido não muda
    assert local(herdado_depois) == {"codigo": BALSAS, "origem": "emissor"}
    assert local(proprio_depois) == {"codigo": PALMAS, "origem": "modelo"}
    assert recarregar(herda).codigo_municipio_prestacao == ""  # nada foi copiado para o modelo


def test_rascunho_guarda_o_que_o_modelo_definia_e_mudar_o_modelo_depois_nao_o_altera(
    empresa_pronta, responsavel
):
    modelo = criar_modelo(codigo_municipio_prestacao=PALMAS)
    nota = gerar(modelo, responsavel)

    with no_esquema():
        ModeloNfse.objects.filter(pk=modelo.pk).update(codigo_municipio_prestacao=BALSAS)

    recarregar(nota)
    assert local(nota) == {"codigo": PALMAS, "origem": "modelo"}


# -- a nota sobrescreve o modelo e volta a herdar -------------------------------------------


def test_a_nota_sobrescreve_o_municipio_do_modelo_e_volta_a_herdar(
    empresa_pronta, responsavel, emissor
):
    modelo = criar_modelo(codigo_municipio_prestacao=PALMAS)
    nota = gerar(modelo, responsavel)
    url = f"{NOTAS}{nota.pk}/"

    ajustada = emissor.patch(url, corpo_da_nota(nota, codigo_municipio_prestacao=SAO_PAULO))
    assert ajustada.status_code == 200, ajustada.json()
    recarregar(nota)
    assert local(nota) == {"codigo": SAO_PAULO, "origem": "nota"}
    assert nota.complementos["municipio_prestacao_modelo"] == PALMAS  # o modelo segue guardado

    emissor.patch(url, corpo_da_nota(nota, codigo_municipio_prestacao=""))  # voltar a herdar
    recarregar(nota)
    assert nota.complementos["municipio_prestacao_nota"] is None
    assert local(nota) == {"codigo": PALMAS, "origem": "modelo"}


def test_editar_o_rascunho_sem_mexer_no_municipio_mantem_o_que_o_modelo_definia(
    empresa_pronta, responsavel, emissor
):
    modelo = criar_modelo(codigo_municipio_prestacao=PALMAS)
    nota = gerar(modelo, responsavel)

    emissor.patch(
        f"{NOTAS}{nota.pk}/", corpo_da_nota(nota, valores={**nota.valores, "servico": "2000.00"})
    )

    recarregar(nota)
    assert local(nota) == {"codigo": PALMAS, "origem": "modelo"}


def test_previa_do_rascunho_corrigido_mostra_o_municipio_do_modelo_como_origem(
    empresa_pronta, responsavel, emissor
):
    modelo = criar_modelo(codigo_municipio_prestacao=PALMAS)
    nota = gerar(modelo, responsavel)

    previa = emissor.post(f"{NOTAS}previa/", corpo_da_nota(nota, rascunho=nota.pk)).json()

    assert previa["complementos"]["local_prestacao"] == {"codigo": PALMAS, "origem": "modelo"}


# -- a API do modelo -------------------------------------------------------------------------


@pytest.fixture
def modelo_api(empresa_pronta, emissor):
    from fiscal.tests.apoio import criar_cadastros_de_teste

    tomador, servico = criar_cadastros_de_teste()
    resposta = emissor.post(
        MODELOS,
        {
            "nome": "Mensalidade",
            "ativo": True,
            "tomador": tomador.pk,
            "servico": servico.pk,
            "valores": {"servico": "1500.00"},
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def test_api_do_modelo_mostra_o_proprio_e_o_efetivo_com_a_origem(emissor, modelo_api):
    corpo = emissor.get(f"{MODELOS}{modelo_api['id']}/").json()

    assert corpo["codigo_municipio_prestacao"] == ""
    assert corpo["local_prestacao_efetivo"] == {"codigo": EMISSOR, "origem": "emissor"}


def test_api_sobrescrever_e_voltar_a_herdar_o_municipio(emissor, modelo_api):
    url = f"{MODELOS}{modelo_api['id']}/"

    sobrescrito = emissor.patch(url, {"codigo_municipio_prestacao": "17.210-00"}).json()
    assert sobrescrito["codigo_municipio_prestacao"] == PALMAS  # só os dígitos valem
    assert sobrescrito["local_prestacao_efetivo"] == {"codigo": PALMAS, "origem": "modelo"}

    for vazio in ("", None):
        emissor.patch(url, {"codigo_municipio_prestacao": PALMAS})
        herdado = emissor.patch(url, {"codigo_municipio_prestacao": vazio}).json()
        assert herdado["codigo_municipio_prestacao"] == ""
        assert herdado["local_prestacao_efetivo"] == {"codigo": EMISSOR, "origem": "emissor"}


@pytest.mark.parametrize(
    ("valor", "trecho"),
    [("9999999", "não encontrado"), ("123", "7 dígitos"), ("35503080", "7 dígitos")],
)
def test_api_recusa_municipio_inexistente_ou_mal_formado(emissor, modelo_api, valor, trecho):
    resposta = emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"codigo_municipio_prestacao": valor})

    assert resposta.status_code == 400
    assert trecho in str(resposta.json()["codigo_municipio_prestacao"])


def test_api_opcoes_traz_o_padrao_do_municipio_da_prestacao(emissor):
    opcoes = emissor.get("/api/agendamentos/opcoes/").json()

    assert opcoes["municipio_prestacao_padrao"] == EMISSOR


def test_api_conferir_o_modelo_mostra_a_incidencia_com_o_municipio_do_modelo(emissor, modelo_api):
    emissor.patch(f"{MODELOS}{modelo_api['id']}/", {"codigo_municipio_prestacao": SAO_PAULO})

    conferencia = emissor.post(f"{MODELOS}{modelo_api['id']}/previa/").json()

    assert conferencia["ok"] is True
    assert conferencia["local_prestacao"] == {"codigo": SAO_PAULO, "origem": "modelo"}
