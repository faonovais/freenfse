"""E-mail da nota: modelos com escape, anexos, fila com retentativa, gatilhos e alertas."""

import datetime as dt
import smtplib

import pytest
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from core.permissoes import Perfil
from documentos import tasks
from documentos.models import ConfiguracaoEmail, EnvioEmail
from documentos.services import contexto, envio_email
from documentos.services.email import fabrica
from documentos.services.email.base import ErroDeEnvio
from documentos.tests.apoio import configurar_email, emitir
from documentos.tests.simulados import SEGREDO_DE_TESTE
from fiscal.models import Certificado
from fiscal.services import emissao, vencimento

pytestmark = pytest.mark.django_db
T = EnvioEmail.Tipo


def _pedir(nota, tipo=T.MANUAL, **extra):
    return envio_email.solicitar(nota, tipo, **extra)


def _mime(provedores, indice=0):
    return provedores.smtp.mensagens[indice]["mime"]


def _anexos(mime):
    return [p.get_filename() for p in mime.walk() if p.get_filename()]


# -- fábrica -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provedor", "classe"),
    [("smtp", "ProvedorSmtp"), ("gmail", "ProvedorGmail"), ("graph", "ProvedorGraph")],
)
def test_a_fabrica_escolhe_o_provedor_da_configuracao(empresa_ativa, provedores, provedor, classe):
    configurar_email(provedor)

    assert type(fabrica.criar_provedor(ConfiguracaoEmail.obter())).__name__ == classe


@pytest.mark.parametrize(
    ("ajustes", "trecho"),
    [
        ({"provedor": "nenhum"}, "não está configurado"),
        ({"smtp_host": ""}, "servidor SMTP"),
        ({"provedor": "graph", "graph_client_secret": None}, "segredo do Microsoft Graph"),
        ({"provedor": "gmail", "gmail_conta_servico": "lixo"}, "JSON válido"),
        ({"remetente_email": ""}, "não está configurado"),
    ],
)
def test_configuracao_incompleta_explica_o_que_falta(empresa_ativa, provedores, ajustes, trecho):
    configurar_email(**{"provedor": "smtp", **ajustes})

    with pytest.raises(ErroDeEnvio) as erro:
        fabrica.criar_provedor(ConfiguracaoEmail.obter())

    assert trecho in erro.value.mensagem and erro.value.temporario is False


# -- envio manual e conteúdo ---------------------------------------------------------------


def test_envio_manual_pelo_smtp_com_variaveis_substituidas_e_os_dois_anexos(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota, valor="1500.00")
    pedido = _pedir(nota)

    situacao = envio_email.processar(pedido.pk)

    assert situacao == "enviado"
    pedido.refresh_from_db()
    assert pedido.enviado_em and pedido.tentativas == 1 and pedido.anexos == ["xml", "pdf"]
    assert pedido.destinatarios == ["financeiro@tomador.test"]
    mime = _mime(provedores)
    assert mime["Subject"] == f"NFS-e nº 1 de {empresa_pronta.razao_social}"
    texto = mime.get_body(("plain",)).get_content()
    assert "Olá, TOMADOR FICTICIO LTDA." in texto and "R$ 1.500,00" in texto
    assert "referente a 10/2026" in texto and nota.chave in texto
    assert _anexos(mime) == ["NFSe-1.xml", "NFSe-1.pdf"]
    xml = next(p for p in mime.walk() if p.get_filename() == "NFSe-1.xml")
    assert xml.get_payload(decode=True) == bytes(nota.xml_nfse)


@pytest.mark.parametrize(
    ("pdf", "xml", "esperado"),
    [
        (True, True, ["pdf", "xml"]),
        (True, False, ["pdf"]),
        (False, True, ["xml"]),
        (False, False, []),
    ],
)
def test_os_anexos_seguem_a_configuracao(
    empresa_pronta, nova_nota, sefin, provedores, pdf, xml, esperado
):
    configurar_email("smtp", anexar_pdf=pdf, anexar_xml=xml)
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)

    envio_email.processar(pedido.pk)

    pedido.refresh_from_db()
    assert sorted(pedido.anexos) == sorted(esperado)
    assert len(_anexos(_mime(provedores))) == len(esperado)


def test_a_sobreposicao_do_modelo_de_nfse_muda_os_anexos(
    empresa_pronta, nova_nota, sefin, provedores, monkeypatch
):
    """Ponto de extensão da Fase 5: o modelo de NFS-e pode desligar o PDF só para as suas notas."""
    configurar_email("smtp", anexar_pdf=True, anexar_xml=True)
    monkeypatch.setattr(envio_email, "_SOBREPOSICOES", [])
    envio_email.registrar_sobreposicao(lambda nfse: {"anexar_pdf": False})
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)

    envio_email.processar(pedido.pk)

    assert _anexos(_mime(provedores)) == ["NFSe-1.xml"]


def test_variaveis_com_html_e_quebras_de_linha_sao_neutralizadas(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    nome_malicioso = 'Cia <script>alert("x")</script> & Filhos\r\nBcc: espiao@mal.test'
    type(nota).objects.filter(pk=nota.pk).update(tomador_nome=nome_malicioso)
    configuracao = ConfiguracaoEmail.obter()
    configuracao.assunto_modelo = "Nota para {nome_tomador}"
    configuracao.save()
    nota.refresh_from_db()
    pedido = _pedir(nota)

    envio_email.processar(pedido.pk)

    mime = _mime(provedores)
    assert "\n" not in mime["Subject"] and "\r" not in mime["Subject"] and mime["Bcc"] is None
    corpo_html = mime.get_body(("html",)).get_content()
    assert "<script>" not in corpo_html
    assert "&lt;script&gt;" in corpo_html and "&amp; Filhos" in corpo_html
    assert "<br>" in corpo_html  # quebras de linha viram <br>, o resto é texto


def test_variavel_desconhecida_e_chave_solta_sao_recusadas_ao_validar(empresa_ativa):
    erros = envio_email.validar_modelos("Nota {numero}", "Olá {nome_tomador} {valor")

    assert "{numero} não existe" in erros["assunto_modelo"]
    assert "sem o '}'" in erros["corpo_modelo"]
    assert envio_email.validar_modelos("{numero_nfse}", "{nome_tomador} {chave} {valor}") == {}


def test_uma_variavel_nova_pode_ser_registrada_por_outra_fase(empresa_ativa, monkeypatch):
    monkeypatch.setattr(envio_email, "_VARIAVEIS", dict(envio_email._VARIAVEIS))
    envio_email.registrar_variavel("vencimento", "Vencimento do boleto", lambda n, e: "10/12/2026")

    assert envio_email.validar_modelos("Vence em {vencimento}", "") == {}
    assert "vencimento" in envio_email.variaveis_disponiveis()


# -- Gmail e Graph pelo mesmo caminho -------------------------------------------------------


@pytest.mark.parametrize("provedor", ["gmail", "graph"])
def test_o_mesmo_pedido_sai_pelo_gmail_e_pelo_graph(
    empresa_pronta, nova_nota, sefin, provedores, provedor
):
    configurar_email(provedor)
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)

    assert envio_email.processar(pedido.pk) == "enviado"

    pedido.refresh_from_db()
    assert pedido.provedor == provedor and pedido.anexos == ["xml", "pdf"]
    if provedor == "gmail":
        assert len(provedores.gmail.enviados) == 1
    else:
        assert len(provedores.graph.chamadas) == 2  # token + sendMail


# -- fila, retentativa e erros -------------------------------------------------------------


def test_falha_temporaria_reagenda_com_espera_crescente_e_depois_envia(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)
    agora = contexto.agora()
    provedores.smtp.falha = smtplib.SMTPServerDisconnected("caiu")

    envio_email.processar(pedido.pk, agora=agora)
    pedido.refresh_from_db()
    assert (pedido.situacao, pedido.tentativas) == ("pendente", 1)
    assert pedido.proxima_tentativa == agora + dt.timedelta(minutes=1)
    assert "tenta de novo" in pedido.erro

    # Antes da hora, nada acontece (nem nova tentativa).
    assert envio_email.processar(pedido.pk, agora=agora + dt.timedelta(seconds=30)) == "pendente"
    pedido.refresh_from_db()
    assert pedido.tentativas == 1

    envio_email.processar(pedido.pk, agora=agora + dt.timedelta(minutes=2))
    pedido.refresh_from_db()
    assert pedido.tentativas == 2
    assert pedido.proxima_tentativa == agora + dt.timedelta(minutes=2) + dt.timedelta(minutes=5)

    provedores.smtp.falha = None
    envio_email.processar(pedido.pk, agora=agora + dt.timedelta(minutes=10))
    pedido.refresh_from_db()
    assert (pedido.situacao, pedido.tentativas, pedido.erro) == ("enviado", 3, "")


def test_depois_do_limite_de_tentativas_o_envio_falha_com_explicacao(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)
    pedido.max_tentativas = 3
    pedido.save()
    provedores.smtp.falha = TimeoutError("lento")
    agora = contexto.agora()

    for n in range(3):
        envio_email.processar(pedido.pk, agora=agora + dt.timedelta(days=n))

    pedido.refresh_from_db()
    assert (pedido.situacao, pedido.tentativas, pedido.proxima_tentativa) == ("falhou", 3, None)
    assert pedido.erro


def test_falha_permanente_nao_tenta_de_novo(empresa_pronta, nova_nota, sefin, provedores):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)
    provedores.smtp.falha = smtplib.SMTPAuthenticationError(535, b"x")

    envio_email.processar(pedido.pk)

    pedido.refresh_from_db()
    assert (pedido.situacao, pedido.tentativas, pedido.proxima_tentativa) == ("falhou", 1, None)
    assert "recusou o usuário ou a senha" in pedido.erro
    assert "SMTP 535" in pedido.erro_tecnico


def test_so_um_processo_pega_a_tentativa(empresa_pronta, nova_nota, sefin, provedores):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)
    agora = contexto.agora()

    assert envio_email._reservar(pedido, agora) is True
    assert envio_email._reservar(pedido, agora) is False  # o outro worker não repete


def test_reenvio_manual_cria_um_novo_registro_com_os_mesmos_destinatarios(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    primeiro = _pedir(nota, destinatarios=["a@x.test", "b@x.test"])
    envio_email.processar(primeiro.pk)

    novo = envio_email.reenviar(primeiro, usuario=None)

    assert novo.pk != primeiro.pk and novo.tipo == T.REENVIO
    assert novo.destinatarios == ["a@x.test", "b@x.test"] and novo.situacao == "pendente"
    assert EnvioEmail.objects.filter(nfse=nota).count() == 2
    assert "email_reenviado" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_envio_manual_sem_destinatario_ou_sem_configuracao_e_recusado_com_motivo(
    empresa_pronta, nova_nota, sefin, provedores
):
    nota = emitir(empresa_pronta, nova_nota)
    with pytest.raises(envio_email.ErroDeEmail, match="não está configurado"):
        _pedir(nota)

    configurar_email("smtp")
    type(nota).objects.filter(pk=nota.pk).update(tomador={**nota.tomador, "emails_envio": []})
    nota.refresh_from_db()
    with pytest.raises(envio_email.ErroDeEmail, match="não tem e-mail de envio"):
        _pedir(nota)


def test_cada_empresa_tem_a_propria_configuracao_e_historico(empresa_a, empresa_b):
    with schema_context(empresa_a.schema_name):
        configurar_email("smtp", remetente_email="a@empresa-a.test")
    with schema_context(empresa_b.schema_name):
        assert ConfiguracaoEmail.obter().provedor == "nenhum"
        assert EnvioEmail.objects.count() == 0
    with schema_context(empresa_a.schema_name):
        assert ConfiguracaoEmail.obter().remetente_email == "a@empresa-a.test"


# -- gatilhos ------------------------------------------------------------------------------


def test_envio_automatico_ao_autorizar_enfileira_uma_vez(
    empresa_pronta, nova_nota, sefin, provedores, fila
):
    configurar_email("smtp", envio_automatico=True)

    nota = emitir(empresa_pronta, nova_nota)

    envios = EnvioEmail.objects.filter(nfse=nota)
    assert [e.tipo for e in envios] == ["autorizacao"] and envios[0].situacao == "pendente"
    assert fila.chamadas == [("processar_envio_email", (empresa_pronta.schema_name, envios[0].pk))]
    from documentos import receptores

    receptores.ao_autorizar(None, nfse=nota)  # o sinal repetido não duplica o e-mail
    assert EnvioEmail.objects.filter(nfse=nota).count() == 1

    envio_email.processar(envios[0].pk)
    assert len(provedores.smtp.mensagens) == 1


def test_sem_envio_automatico_nada_e_enfileirado(
    empresa_pronta, nova_nota, sefin, provedores, fila
):
    configurar_email("smtp", envio_automatico=False)

    emitir(empresa_pronta, nova_nota)

    assert EnvioEmail.objects.count() == 0 and fila.chamadas == []


def test_envio_automatico_de_tomador_sem_email_fica_registrado_como_falha(
    empresa_pronta, nova_nota, sefin, provedores, fila
):
    configurar_email("smtp", envio_automatico=True)
    from fiscal.tests.apoio import criar_cadastros_de_teste

    tomador, _ = criar_cadastros_de_teste()
    tomador.emails_envio = []
    tomador.save()
    nota = emitir(empresa_pronta, nova_nota)

    envio = EnvioEmail.objects.get(nfse=nota)
    assert envio.situacao == "falhou" and "não tem e-mail de envio" in envio.erro
    assert fila.chamadas == []  # nada para enviar


def test_aviso_de_cancelamento_vai_so_se_estiver_ligado(
    empresa_pronta, nova_nota, sefin, provedores, fila
):
    configurar_email("smtp", avisar_cancelamento=True)
    nota = emitir(empresa_pronta, nova_nota)

    emissao.cancelar(
        empresa_pronta,
        nota,
        codigo_motivo=1,
        justificativa="Nota emitida com valor errado.",
        usuario=None,
    )

    envio = EnvioEmail.objects.get(nfse=nota, tipo="cancelamento")
    envio_email.processar(envio.pk)
    mime = _mime(provedores)
    assert mime["Subject"].startswith("CANCELADA — ")
    assert "Esta nota foi CANCELADA" in mime.get_body(("plain",)).get_content()
    assert mime.get_body(("html",)).get_content().count("CANCELADA") >= 1


def test_enviar_teste_registra_sucesso_e_falha(empresa_ativa, provedores):
    configurar_email("smtp")

    ok = envio_email.enviar_teste("dono@empresa.test", usuario=None)
    provedores.smtp.falha = smtplib.SMTPAuthenticationError(535, b"x")
    falha = envio_email.enviar_teste("dono@empresa.test", usuario=None)

    assert (ok.situacao, falha.situacao) == ("enviado", "falhou")
    assert "recusou o usuário" in falha.erro
    assert ok.tipo == T.TESTE and ok.nfse_id is None


# -- alerta de certificado -----------------------------------------------------------------


def _vence_em(dias, agora):
    Certificado.objects.all().delete()
    return Certificado.objects.create(
        arquivo_pfx=b"x",
        senha="s",
        titular="T",
        cnpj_titular="11222333000181",
        valido_de=agora - dt.timedelta(days=300),
        valido_ate=agora + dt.timedelta(days=dias, hours=1),
        impressao_digital="b" * 64,
    )


def test_o_alerta_de_certificado_vira_email_para_os_administradores(
    empresa_a, usuario, vincular, provedores, fila
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    agora = contexto.agora()
    with schema_context(empresa_a.schema_name):
        configurar_email("smtp")
        _vence_em(7, agora)

    vencimento.verificar_certificados(agora)
    vencimento.verificar_certificados(agora)  # repetir não duplica

    with schema_context(empresa_a.schema_name):
        envio = EnvioEmail.objects.get(tipo="alerta_certificado")
        assert envio.destinatarios == [usuario.email] and envio.nfse_id is None
        assert "vence em 7 dia(s)" in envio.assunto
        assert fila.nomes() == ["processar_envio_email"]
        envio_email.processar(envio.pk)
        assert "Certificado A1" in _mime(provedores).get_body(("plain",)).get_content()


def test_o_alerta_usa_a_lista_da_configuracao_quando_ela_existe(
    empresa_a, usuario, vincular, provedores
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    agora = contexto.agora()
    with schema_context(empresa_a.schema_name):
        configurar_email("smtp", emails_alerta=["ti@empresa-alfa.test"])
        _vence_em(7, agora)

    vencimento.verificar_certificados(agora)

    with schema_context(empresa_a.schema_name):
        assert EnvioEmail.objects.get(tipo="alerta_certificado").destinatarios == [
            "ti@empresa-alfa.test"
        ]


def test_sem_email_configurado_o_alerta_nao_gera_envio(empresa_a, usuario, vincular, fila):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    agora = contexto.agora()
    with schema_context(empresa_a.schema_name):
        _vence_em(7, agora)

    vencimento.verificar_certificados(agora)

    with schema_context(empresa_a.schema_name):
        assert EnvioEmail.objects.count() == 0 and fila.chamadas == []


# -- rotina periódica ----------------------------------------------------------------------


def test_a_rotina_periodica_enfileira_so_os_emails_vencidos(empresa_ativa, fila, monkeypatch):
    configurar_email("smtp")
    agora = contexto.agora()
    vencido = EnvioEmail.objects.create(
        tipo=T.TESTE, destinatarios=["a@x.test"], proxima_tentativa=agora - dt.timedelta(minutes=1)
    )
    EnvioEmail.objects.create(
        tipo=T.TESTE, destinatarios=["a@x.test"], proxima_tentativa=agora + dt.timedelta(hours=1)
    )
    EnvioEmail.objects.create(tipo=T.TESTE, situacao="enviado", destinatarios=["a@x.test"])

    resultado = tasks.despachar_pendentes()

    assert resultado["emails"] == 1
    assert fila.chamadas == [("processar_envio_email", (empresa_ativa.schema_name, vencido.pk))]


def test_a_senha_nao_aparece_em_mensagem_de_erro_nem_no_registro(
    empresa_pronta, nova_nota, sefin, provedores
):
    configurar_email("smtp")
    nota = emitir(empresa_pronta, nova_nota)
    pedido = _pedir(nota)
    provedores.smtp.falha = smtplib.SMTPAuthenticationError(535, SEGREDO_DE_TESTE.encode())

    envio_email.processar(pedido.pk)

    pedido.refresh_from_db()
    visivel = f"{pedido.erro} {pedido.erro_tecnico} {pedido.assunto} {pedido.destinatarios}"
    assert SEGREDO_DE_TESTE not in visivel
