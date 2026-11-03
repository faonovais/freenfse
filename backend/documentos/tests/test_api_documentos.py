"""API de documentos: permissões, isolamento, credenciais que nunca saem e download só do dono."""

import logging

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from cadastros.tests.conftest import Api
from core.models import LogAuditoria
from core.permissoes import Perfil
from documentos.models import ConfiguracaoDrive, ConfiguracaoEmail, EnvioEmail, Exportacao
from documentos.services import envio_email
from documentos.tests.apoio import ativar_drive, configurar_email, emitir, nota_avulsa
from documentos.tests.simulados import SEGREDO_DE_TESTE, conta_de_servico_json

pytestmark = pytest.mark.django_db
BASE = "/api/documentos/"
EMAIL = f"{BASE}config/email/"
DRIVE = f"{BASE}config/drive/"
EXPORTACOES = f"{BASE}exportacoes/"


def _corpo_email(**extra):
    base = {
        "provedor": "smtp",
        "remetente_email": "notas@empresa-alfa.test",
        "smtp_host": "smtp.exemplo.test",
        "smtp_usuario": "notas@empresa-alfa.test",
        "smtp_senha": SEGREDO_DE_TESTE,
    }
    base.update(extra)
    return base


def _coluna(tabela, coluna):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {coluna} FROM {tabela}")  # noqa: S608 - nomes fixos do teste
        return cursor.fetchone()[0]


# -- permissões ----------------------------------------------------------------------------


def test_configuracao_de_email_e_so_do_administrador_para_alterar(api_de, empresa_a):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)

    assert admin.put(EMAIL, _corpo_email()).status_code == 200
    assert admin.get(EMAIL).status_code == 200


def test_consulta_le_a_configuracao_mas_nao_altera_e_o_emissor_nem_le(
    api_de, cliente_de, vincular, empresa_a
):
    from core.models import Usuario

    consulta = api_de(empresa_a, Perfil.CONSULTA)
    emissor_usuario = Usuario.objects.create_user(
        email="emissor@exemplo.test", password="x" * 14, nome="E"
    )
    vincular(emissor_usuario, empresa_a, Perfil.EMISSOR)
    emissor = Api(cliente_de(emissor_usuario), empresa_a)

    assert consulta.get(EMAIL).status_code == 200 and consulta.get(DRIVE).status_code == 200
    assert consulta.put(EMAIL, _corpo_email()).status_code == 403
    assert consulta.put(DRIVE, {"ativo": False}).status_code == 403
    assert consulta.post(f"{EMAIL}teste/", {"destino": "a@x.test"}).status_code == 403
    assert emissor.get(EMAIL).status_code == 403  # o Emissor não tem config.consultar (issue #14)


def test_sem_vinculo_com_a_empresa_nao_ha_acesso(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    cliente = cliente_de(usuario)

    assert cliente.get(EMAIL, HTTP_X_EMPRESA=str(empresa_b.pk)).status_code == 403
    assert cliente_de().get(EMAIL, HTTP_X_EMPRESA=str(empresa_a.pk)).status_code in (401, 403)


# -- credenciais nunca saem ----------------------------------------------------------------


def test_as_credenciais_de_email_ficam_cifradas_e_nunca_voltam(api_de, empresa_a, caplog):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)
    chave_gmail = conta_de_servico_json()
    corpo = _corpo_email(
        graph_tenant_id="11111111-1111-1111-1111-111111111111",
        graph_client_id="22222222-2222-2222-2222-222222222222",
        graph_client_secret=SEGREDO_DE_TESTE + "-graph",
        gmail_conta_servico=chave_gmail,
    )
    caplog.set_level(logging.DEBUG)

    resposta = admin.put(EMAIL, corpo)
    leitura = admin.get(EMAIL)

    saidas = resposta.content.decode() + leitura.content.decode()
    for segredo in (
        SEGREDO_DE_TESTE,
        "BEGIN PRIVATE KEY",
        "private_key",
        SEGREDO_DE_TESTE + "-graph",
    ):
        assert segredo not in saidas
    assert leitura.json()["credenciais_configuradas"] == {
        "smtp_senha": True, "graph_client_secret": True, "gmail_conta_servico": True,
    }  # fmt: skip
    with schema_context(empresa_a.schema_name):
        for coluna in ("smtp_senha", "graph_client_secret", "gmail_conta_servico"):
            bruto = _coluna("documentos_configuracaoemail", coluna)
            assert bruto.startswith("v1:")
            assert SEGREDO_DE_TESTE not in bruto and "PRIVATE KEY" not in bruto
        assert ConfiguracaoEmail.obter().smtp_senha == SEGREDO_DE_TESTE  # o modelo decifra
    registro = LogAuditoria.objects.get(acao="email_config_alterada")
    assert SEGREDO_DE_TESTE not in str(registro.detalhes) and "BEGIN" not in str(registro.detalhes)
    assert "smtp_senha" in registro.detalhes["campos"]  # só o NOME do campo alterado
    assert SEGREDO_DE_TESTE not in caplog.text and "PRIVATE KEY" not in caplog.text


def test_credencial_ausente_ou_vazia_e_mantida_e_null_apaga(api_de, empresa_a):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)
    admin.put(EMAIL, _corpo_email())

    admin.put(EMAIL, _corpo_email(smtp_senha=""))
    with schema_context(empresa_a.schema_name):
        assert ConfiguracaoEmail.obter().smtp_senha == SEGREDO_DE_TESTE
    corpo = _corpo_email()
    corpo.pop("smtp_senha")
    admin.put(EMAIL, corpo)
    with schema_context(empresa_a.schema_name):
        assert ConfiguracaoEmail.obter().smtp_senha == SEGREDO_DE_TESTE

    admin.put(EMAIL, _corpo_email(smtp_senha=None))
    with schema_context(empresa_a.schema_name):
        assert ConfiguracaoEmail.obter().smtp_senha is None
    assert admin.get(EMAIL).json()["credenciais_configuradas"]["smtp_senha"] is False


def test_a_conta_de_servico_do_drive_fica_cifrada_e_so_o_email_volta(
    api_de, empresa_a, drive_simulado, caplog
):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)
    caplog.set_level(logging.DEBUG)

    resposta = admin.put(
        DRIVE,
        {"ativo": True, "conta_servico": conta_de_servico_json(), "pasta_raiz_id": "RAIZ"},
    )

    assert resposta.status_code == 200, resposta.content
    texto = resposta.content.decode() + admin.get(DRIVE).content.decode()
    assert "private_key" not in texto and "BEGIN PRIVATE KEY" not in texto
    dados = admin.get(DRIVE).json()
    assert (
        dados["conta_servico_configurada"] is True and dados["pasta_raiz_nome"] == "Notas Fiscais"
    )
    assert dados["conta_servico_email"].endswith("iam.gserviceaccount.com")
    with schema_context(empresa_a.schema_name):
        bruto = _coluna("documentos_configuracaodrive", "conta_servico")
    assert bruto.startswith("v1:") and "PRIVATE KEY" not in bruto
    detalhes = str(LogAuditoria.objects.get(acao="drive_config_alterada").detalhes)
    assert "PRIVATE KEY" not in detalhes and "private_key" not in detalhes
    assert "PRIVATE KEY" not in caplog.text


# -- validação da configuração -------------------------------------------------------------


@pytest.mark.parametrize(
    ("corpo", "campo"),
    [
        (_corpo_email(assunto_modelo="Nota {numero}"), "assunto_modelo"),
        (_corpo_email(corpo_modelo="Olá {nome_tomador"), "corpo_modelo"),
        (_corpo_email(smtp_host=""), "smtp_host"),
        (_corpo_email(remetente_email=""), "remetente_email"),
        (_corpo_email(copias_fixas=["isto-nao-e-email"]), "copias_fixas"),
        (_corpo_email(provedor="graph", graph_tenant_id=""), "graph_tenant_id"),
        (_corpo_email(provedor="gmail", gmail_conta_servico="lixo"), "gmail_conta_servico"),
        (_corpo_email(provedor="outro"), "provedor"),
    ],
)
def test_erros_da_configuracao_de_email_apontam_o_campo(api_de, empresa_a, corpo, campo):
    resposta = api_de(empresa_a, Perfil.ADMINISTRADOR).put(EMAIL, corpo)

    assert resposta.status_code == 400 and campo in resposta.json()


def test_erros_da_configuracao_do_drive_vem_todos_juntos(api_de, empresa_a, drive_simulado):
    resposta = api_de(empresa_a, Perfil.ADMINISTRADOR).put(
        DRIVE,
        {
            "ativo": True,
            "conta_servico": conta_de_servico_json(),
            "pasta_raiz_id": "NAO-EXISTE",
            "modelo_subpastas": "{ano}//{x}",
            "modelo_arquivo": "{y",
        },
    )

    assert resposta.status_code == 400
    assert {"pasta_raiz_id", "modelo_subpastas", "modelo_arquivo"} <= set(resposta.json())


def test_previa_do_drive_valida_e_mostra_uma_nota_real(api_de, empresa_a):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)
    with schema_context(empresa_a.schema_name):
        nota = nota_avulsa(42)

    invalida = admin.post(
        f"{DRIVE}previa/", {"modelo_subpastas": "{ano}", "modelo_arquivo": "{numero_nfse}"}
    )
    valida = admin.post(
        f"{DRIVE}previa/",
        {"modelo_subpastas": "{ano}/{mes}", "modelo_arquivo": "NFSe {numero_nfse} - {chave}"},
    )

    assert invalida.status_code == 400 and "unicidade" in invalida.json()
    corpo = valida.json()
    assert corpo["nota"] == nota.pk and corpo["previa"]["pasta"] == "2026/11"
    assert corpo["previa"]["arquivos"][0] == f"2026/11/NFSe 42 - {nota.chave}.xml"


def test_previa_sem_nenhuma_nota_explica(api_de, empresa_a):
    resposta = api_de(empresa_a, Perfil.ADMINISTRADOR).post(f"{DRIVE}previa/", {})

    assert resposta.status_code == 200 and resposta.json()["previa"] is None


# -- teste, envios por nota e reenvios -----------------------------------------------------


def test_email_de_teste_pela_api(api_de, empresa_a, provedores):
    admin = api_de(empresa_a, Perfil.ADMINISTRADOR)
    admin.put(EMAIL, _corpo_email())

    resposta = admin.post(f"{EMAIL}teste/", {"destino": "dono@empresa-alfa.test"})

    assert resposta.status_code == 200 and resposta.json()["situacao"] == "enviado"
    assert resposta.json()["tipo"] == "teste" and len(provedores.smtp.mensagens) == 1
    assert admin.post(f"{EMAIL}teste/", {"destino": "invalido"}).status_code == 400


def test_historico_envio_manual_e_reenvio_pela_api(
    api_de, empresa_pronta, nova_nota, sefin, provedores, fila
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    emissor = api_de(empresa_pronta, Perfil.EMISSOR)
    url = f"{BASE}notas/{nota.pk}/"

    vazio = emissor.get(f"{url}envios/").json()
    assert vazio["emails"] == [] and vazio["destinatarios_padrao"] == ["financeiro@tomador.test"]
    assert vazio["email_configurado"] is True and vazio["drive_ativo"] is False

    enviado = emissor.post(f"{url}email/", {"destinatarios": ["Outro@Cliente.test"]})
    assert enviado.status_code == 202
    assert enviado.json()["destinatarios"] == ["outro@cliente.test"]  # normalizado
    assert fila.nomes() == ["processar_envio_email"]
    with schema_context(empresa_pronta.schema_name):
        envio_email.processar(enviado.json()["id"])

    historico = emissor.get(f"{url}envios/").json()["emails"]
    assert [(e["tipo"], e["situacao"]) for e in historico] == [("manual", "enviado")]
    reenviado = emissor.post(f"{BASE}envios-email/{enviado.json()['id']}/reenviar/")
    assert reenviado.status_code == 202 and reenviado.json()["tipo"] == "reenvio"
    assert reenviado.json()["destinatarios"] == ["outro@cliente.test"]


def test_consulta_ve_o_historico_mas_nao_envia(
    api_de, empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    consulta = api_de(empresa_pronta, Perfil.CONSULTA)

    assert consulta.get(f"{BASE}notas/{nota.pk}/envios/").status_code == 200
    assert consulta.post(f"{BASE}notas/{nota.pk}/email/", {}).status_code == 403
    assert consulta.post(f"{BASE}notas/{nota.pk}/drive/reenviar/").status_code == 403
    assert consulta.post(f"{BASE}drive/reenviar-periodo/", {}).status_code == 403
    assert consulta.post(f"{BASE}envios-email/1/reenviar/").status_code == 403


def test_envio_manual_recusado_com_motivo(api_de, empresa_pronta, nova_nota, sefin, provedores):
    emissor = api_de(empresa_pronta, Perfil.EMISSOR)
    rascunho = nova_nota()
    nota = emitir(empresa_pronta, nova_nota)

    sem_config = emissor.post(f"{BASE}notas/{nota.pk}/email/", {})
    with schema_context(empresa_pronta.schema_name):
        configurar_email("smtp")
    nao_emitida = emissor.post(f"{BASE}notas/{rascunho.pk}/email/", {})

    assert sem_config.status_code == 409 and "não está configurado" in sem_config.json()["detalhe"]
    assert nao_emitida.status_code == 409 and nao_emitida.json()["codigo"] == "nota_nao_emitida"
    assert emissor.get(f"{BASE}notas/99999/envios/").status_code == 404


def test_reenviar_ao_drive_por_nota_e_por_periodo(api_de, empresa_a, fila):
    emissor = api_de(empresa_a, Perfil.EMISSOR)
    with schema_context(empresa_a.schema_name):
        nova = nota_avulsa(
            1,
            emitida_em=__import__("datetime").datetime(
                2026, 11, 20, 15, tzinfo=__import__("datetime").UTC
            ),
        )
        velha = nota_avulsa(
            2,
            emitida_em=__import__("datetime").datetime(
                2026, 10, 5, 15, tzinfo=__import__("datetime").UTC
            ),
        )
        nota_avulsa(3, situacao="rascunho")
    desligado = emissor.post(f"{BASE}notas/{nova.pk}/drive/reenviar/")
    with schema_context(empresa_a.schema_name):
        ativar_drive()

    por_nota = emissor.post(f"{BASE}notas/{nova.pk}/drive/reenviar/")
    por_periodo = emissor.post(
        f"{BASE}drive/reenviar-periodo/",
        {"periodo_inicio": "2026-10-01", "periodo_fim": "2026-10-31"},
    )

    assert desligado.status_code == 409 and desligado.json()["codigo"] == "drive_desligado"
    assert por_nota.status_code == 202 and por_periodo.json() == {"enfileiradas": 1}
    ids_enfileirados = [a[1] for a in fila.chamadas]
    assert (empresa_a.schema_name, nova.pk, True) in ids_enfileirados
    assert (empresa_a.schema_name, velha.pk, True) in ids_enfileirados


def test_reenviar_periodo_grande_demais_e_recusado(api_de, empresa_a, settings):
    settings.FREENFSE_LOTE_MAX_NOTAS = 1
    emissor = api_de(empresa_a, Perfil.EMISSOR)
    with schema_context(empresa_a.schema_name):
        ativar_drive()
        nota_avulsa(1)
        nota_avulsa(2)

    resposta = emissor.post(f"{BASE}drive/reenviar-periodo/", {})

    assert resposta.status_code == 409 and resposta.json()["codigo"] == "periodo_grande"


# -- download em lote pela API ------------------------------------------------------------


def _usuario(vincular, empresa, email, perfil, cliente_de):
    from core.models import Usuario

    usuario = Usuario.objects.create_user(email=email, password="x" * 14, nome=email.split("@")[0])
    vincular(usuario, empresa, perfil)
    return Api(cliente_de(usuario), empresa), usuario


def _gerar(api, empresa, fila):
    pedido = api.post(EXPORTACOES, {})
    assert pedido.status_code == 202, pedido.content
    from documentos.services import exportacao

    with schema_context(empresa.schema_name):
        exportacao.gerar(pedido.json()["id"])
    return pedido.json()["id"]


def _baixar(api, pedido_id):
    return api.get(f"{EXPORTACOES}{pedido_id}/download/")


def test_pedido_de_lote_enfileira_e_o_dono_baixa_o_zip(
    empresa_pronta, nova_nota, sefin, vincular, cliente_de, fila
):
    emitir(empresa_pronta, nova_nota)
    api, _ = _usuario(
        vincular, empresa_pronta, "financeiro@exemplo.test", Perfil.FINANCEIRO, cliente_de
    )

    pedido_id = _gerar(api, empresa_pronta, fila)

    assert fila.nomes() == ["gerar_exportacao"]
    estado = api.get(f"{EXPORTACOES}{pedido_id}/").json()
    assert estado["situacao"] == "pronta" and estado["processadas"] == estado["total"] == 1
    resposta = _baixar(api, pedido_id)
    assert resposta.status_code == 200 and resposta["Content-Type"] == "application/zip"
    assert "attachment" in resposta["Content-Disposition"]
    conteudo = b"".join(resposta.streaming_content)
    import io
    import zipfile

    assert "resumo.csv" in zipfile.ZipFile(io.BytesIO(conteudo)).namelist()


def test_outro_usuario_da_mesma_empresa_nao_baixa_nem_ve_o_pedido(
    empresa_pronta, nova_nota, sefin, vincular, cliente_de, fila, master
):
    emitir(empresa_pronta, nova_nota)
    dono, _ = _usuario(vincular, empresa_pronta, "dono@exemplo.test", Perfil.EMISSOR, cliente_de)
    colega, _ = _usuario(
        vincular, empresa_pronta, "colega@exemplo.test", Perfil.ADMINISTRADOR, cliente_de
    )
    administrador_global = Api(cliente_de(master), empresa_pronta)
    pedido_id = _gerar(dono, empresa_pronta, fila)

    for estranho in (colega, administrador_global):
        assert _baixar(estranho, pedido_id).status_code == 404
        assert estranho.get(f"{EXPORTACOES}{pedido_id}/").status_code == 404
        assert estranho.get(EXPORTACOES).json() == []
    assert _baixar(dono, pedido_id).status_code == 200
    assert len(dono.get(EXPORTACOES).json()) == 1


def test_pedido_de_uma_empresa_nao_aparece_nem_baixa_na_outra(
    empresa_b, empresa_pronta, nova_nota, sefin, vincular, cliente_de, fila, usuario
):
    emitir(empresa_pronta, nova_nota)
    vincular(usuario, empresa_pronta, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    cliente = cliente_de(usuario)
    em_a, em_b = Api(cliente, empresa_pronta), Api(cliente, empresa_b)
    pedido_id = _gerar(em_a, empresa_pronta, fila)

    assert _baixar(em_b, pedido_id).status_code == 404
    assert em_b.get(EXPORTACOES).json() == []
    assert _baixar(em_a, pedido_id).status_code == 200


def test_sem_a_permissao_de_exportar_nao_ha_lote(api_de, empresa_a, vincular):
    consulta = api_de(empresa_a, Perfil.CONSULTA)

    assert consulta.post(EXPORTACOES, {}).status_code == 403
    assert consulta.get(EXPORTACOES).status_code == 403
    assert consulta.get(f"{EXPORTACOES}1/download/").status_code == 403


def test_quem_perdeu_o_vinculo_nao_baixa_mais(
    empresa_pronta, nova_nota, sefin, vincular, cliente_de, fila
):
    from core.models import VinculoUsuarioEmpresa

    emitir(empresa_pronta, nova_nota)
    api, usuario = _usuario(
        vincular, empresa_pronta, "saiu@exemplo.test", Perfil.EMISSOR, cliente_de
    )
    pedido_id = _gerar(api, empresa_pronta, fila)
    VinculoUsuarioEmpresa.objects.filter(usuario=usuario).update(ativo=False)

    assert _baixar(api, pedido_id).status_code == 403


def test_pedido_acima_do_limite_volta_400_com_o_motivo(api_de, empresa_a, settings, fila):
    settings.FREENFSE_LOTE_MAX_NOTAS = 1
    api = api_de(empresa_a, Perfil.EMISSOR)
    with schema_context(empresa_a.schema_name):
        nota_avulsa(1)
        nota_avulsa(2)

    resposta = api.post(EXPORTACOES, {})

    assert resposta.status_code == 400 and "limite" in resposta.json()["detalhe"]
    assert fila.chamadas == []
    with schema_context(empresa_a.schema_name):
        assert Exportacao.objects.count() == 0
    assert api.post(EXPORTACOES, {"competencia": "2026-13"}).status_code == 400


def test_download_expirado_volta_409(empresa_pronta, nova_nota, sefin, vincular, cliente_de, fila):
    emitir(empresa_pronta, nova_nota)
    api, _ = _usuario(vincular, empresa_pronta, "dono2@exemplo.test", Perfil.EMISSOR, cliente_de)
    pedido_id = _gerar(api, empresa_pronta, fila)
    from documentos.services import exportacao

    with schema_context(empresa_pronta.schema_name):
        exportacao.expurgar(agora=exportacao.contexto.agora().replace(year=2100))

    resposta = _baixar(api, pedido_id)

    assert resposta.status_code == 409 and resposta.json()["codigo"] == "download_indisponivel"


def test_a_configuracao_de_uma_empresa_nao_vaza_para_a_outra(
    api_de, empresa_a, empresa_b, usuario, vincular, cliente_de
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    vincular(usuario, empresa_b, Perfil.ADMINISTRADOR)
    cliente = cliente_de(usuario)
    em_a, em_b = Api(cliente, empresa_a), Api(cliente, empresa_b)
    em_a.put(EMAIL, _corpo_email(remetente_email="a@empresa-a.test"))

    assert em_a.get(EMAIL).json()["remetente_email"] == "a@empresa-a.test"
    dados_b = em_b.get(EMAIL).json()
    assert (
        dados_b["provedor"] == "nenhum"
        and dados_b["credenciais_configuradas"]["smtp_senha"] is False
    )
    with schema_context(empresa_b.schema_name):
        assert not EnvioEmail.objects.exists() and not ConfiguracaoDrive.obter().ativo
