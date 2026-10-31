"""Envio de e-mail das notas: modelos, anexos, fila persistida com retentativa e registro.

Cada e-mail vira um `EnvioEmail` na hora do pedido; um processo "reserva" a tentativa, envia pelo
provedor da empresa e grava o resultado. Falha **temporária** (rede, limite, serviço fora do ar)
reagenda com espera crescente (`proxima_tentativa`, persistida: sobrevive à queda do worker);
falha **permanente** (senha recusada, destinatário inexistente) encerra com explicação simples.
"""

import html
import logging
import re

from core.models import LogAuditoria, VinculoUsuarioEmpresa
from core.permissoes import Perfil
from core.services import auditoria
from documentos.models import ConfiguracaoEmail, EnvioEmail
from documentos.services import contexto, modelos_texto
from documentos.services.email import fabrica
from documentos.services.email.base import ErroDeEnvio, MensagemEmail
from fiscal.services import emissao

logger = logging.getLogger(__name__)

T = EnvioEmail.Tipo
S = EnvioEmail.Situacao
LIMITE_DE_ANEXO_BYTES = 20 * 1024 * 1024
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]+")


class ErroDeEmail(Exception):
    """Pedido de e-mail recusado por algo que o usuário entende e corrige."""


# --- Variáveis dos modelos (extensível) ----------------------------------------------------

_VARIAVEIS = {}


def registrar_variavel(nome, descricao, funcao):
    """Inclui uma variável `{nome}` nos modelos de e-mail; `funcao(nfse, empresa)` dá o texto.

    É o ponto de extensão das próximas fases (por exemplo, `{vencimento}` com os boletos).
    """
    _VARIAVEIS[nome] = (descricao, funcao)


def _dinheiro(valor):
    inteiro, _, centavos = f"{float(valor):,.2f}".partition(".")
    return f"{inteiro.replace(',', '.')},{centavos}"


registrar_variavel("numero_nfse", "Número da NFS-e", lambda n, e: n.numero_nfse or "")
registrar_variavel("nome_tomador", "Nome do tomador", lambda n, e: n.tomador_nome)
registrar_variavel("valor", "Valor do serviço (1.500,00)", lambda n, e: _dinheiro(n.valor_servico))
registrar_variavel("competencia", "Competência (MM/AAAA)", lambda n, e: f"{n.competencia:%m/%Y}")
registrar_variavel("chave", "Chave de acesso", lambda n, e: n.chave or "")
registrar_variavel("nome_emitente", "Razão social da empresa emitente", lambda n, e: e.razao_social)
registrar_variavel("cnpj_emitente", "CNPJ da empresa emitente", lambda n, e: e.cnpj)
registrar_variavel(
    "data_emissao",
    "Data de emissão (DD/MM/AAAA)",
    lambda n, e: f"{n.emitida_em:%d/%m/%Y}" if n.emitida_em else "",
)


def variaveis_disponiveis():
    """Nome → descrição das variáveis que os modelos aceitam."""
    return {nome: descricao for nome, (descricao, _f) in _VARIAVEIS.items()}


def valores_da_nota(nfse, empresa):
    """Valor de cada variável para a nota."""
    return {nome: funcao(nfse, empresa) for nome, (_d, funcao) in _VARIAVEIS.items()}


def validar_modelos(assunto, corpo):
    """Erros por campo (`assunto_modelo`, `corpo_modelo`): variável desconhecida ou chave solta."""
    erros = {}
    for campo, texto in (("assunto_modelo", assunto), ("corpo_modelo", corpo)):
        problemas, _usadas = modelos_texto.analisar(texto, set(_VARIAVEIS))
        if problemas:
            erros[campo] = " ".join(problemas)
    return erros


# --- Sobreposição por modelo de NFS-e (a Fase 5 registra o seu) ----------------------------

_SOBREPOSICOES = []


def registrar_sobreposicao(funcao):
    """Registra `funcao(nfse) -> dict` que ajusta o envio por modelo de NFS-e (Fase 5).

    As chaves aceitas: `anexar_pdf`, `anexar_xml`, `envio_automatico`, `avisar_cancelamento`,
    `assunto_modelo`, `corpo_modelo` e `copias_fixas`. Sem nenhuma registrada, vale a configuração
    da empresa.
    """
    _SOBREPOSICOES.append(funcao)


def configuracao_efetiva(configuracao, nfse):
    """Configuração da empresa com as sobreposições do modelo de NFS-e da nota aplicadas."""
    valores = {
        campo: getattr(configuracao, campo)
        for campo in (
            "anexar_pdf",
            "anexar_xml",
            "envio_automatico",
            "avisar_cancelamento",
            "assunto_modelo",
            "corpo_modelo",
            "copias_fixas",
        )
    }
    for funcao in _SOBREPOSICOES:
        valores.update(funcao(nfse) or {})
    return valores


# --- Montagem da mensagem ------------------------------------------------------------------


def _linha_unica(texto):
    """Cabeçalho sem quebra de linha nem caractere de controle (evita injeção de cabeçalho)."""
    return " ".join(_CONTROLE.sub(" ", str(texto)).split())


def renderizar(efetiva, nfse, empresa):
    """`(assunto, texto, html)` da mensagem. O HTML escapa tudo, inclusive o texto do modelo."""
    valores = valores_da_nota(nfse, empresa)
    assunto = _linha_unica(modelos_texto.renderizar(efetiva["assunto_modelo"], valores))
    texto = modelos_texto.renderizar(efetiva["corpo_modelo"], valores)
    paragrafos = [html.escape(p).replace("\n", "<br>") for p in texto.split("\n\n")]
    corpo_html = "".join(f"<p>{p}</p>" for p in paragrafos)
    return assunto, texto, f"<html><body>{corpo_html}</body></html>"


def destinatarios_da_nota(nfse):
    """E-mails de envio do tomador (cópia gravada na nota)."""
    return [e for e in (nfse.tomador or {}).get("emails_envio", []) if e]


def _anexos(efetiva, nfse, empresa):
    anexos, nomes = [], []
    if efetiva["anexar_xml"] and nfse.xml_nfse:
        anexos.append(
            (f"NFSe-{nfse.numero_nfse or nfse.pk}.xml", "application/xml", bytes(nfse.xml_nfse))
        )
        nomes.append("xml")
    if efetiva["anexar_pdf"]:
        pdf = emissao.gerar_danfse(empresa, nfse)
        anexos.append((f"NFSe-{nfse.numero_nfse or nfse.pk}.pdf", "application/pdf", pdf))
        nomes.append("pdf")
    if sum(len(a[2]) for a in anexos) > LIMITE_DE_ANEXO_BYTES:
        raise ErroDeEnvio(
            "Os anexos passam de 20 MB. Desligue um deles na configuração de e-mail.",
            temporario=False,
        )
    return anexos, nomes


# --- Pedido, fila e envio ------------------------------------------------------------------


def _quem(usuario):
    return {
        "criado_por_id": getattr(usuario, "pk", None),
        "criado_por_email": getattr(usuario, "email", "") or "",
    }


def solicitar(nfse, tipo, *, usuario=None, destinatarios=None, chave_idempotencia=None, agora=None):
    """Cria o `EnvioEmail` pendente da nota (ou devolve o existente da mesma chave de idempotência).

    Levanta `ErroDeEmail` se o e-mail não está configurado ou não há para quem enviar — exceto
    nos envios automáticos, que registram a falha no histórico em vez de interromper a emissão.
    """
    agora = agora or contexto.agora()
    configuracao = ConfiguracaoEmail.obter()
    automatico = tipo in (T.AUTORIZACAO, T.CANCELAMENTO)
    if chave_idempotencia:
        existente = EnvioEmail.objects.filter(chave_idempotencia=chave_idempotencia).first()
        if existente:
            return existente
    efetiva = configuracao_efetiva(configuracao, nfse)
    para = list(destinatarios) if destinatarios else destinatarios_da_nota(nfse)
    erro = ""
    if configuracao.provedor == ConfiguracaoEmail.Provedor.NENHUM:
        erro = "O envio de e-mail não está configurado (Configuração › E-mail)."
    elif not para:
        erro = "O tomador não tem e-mail de envio cadastrado. Cadastre em Cadastros › Pessoas."
    if erro and not automatico:
        raise ErroDeEmail(erro)
    envio = EnvioEmail.objects.create(
        nfse=nfse,
        tipo=tipo,
        situacao=S.FALHOU if erro else S.PENDENTE,
        provedor=configuracao.provedor,
        destinatarios=para,
        copias=list(efetiva["copias_fixas"] or []),
        erro=erro,
        chave_idempotencia=chave_idempotencia,
        proxima_tentativa=None if erro else agora,
        **_quem(usuario),
    )
    return envio


def _reservar(envio, agora):
    """Reserva a tentativa: só um processo a pega, mesmo com dois workers."""
    reservado = EnvioEmail.objects.filter(
        pk=envio.pk, situacao=S.PENDENTE, proxima_tentativa__lte=agora
    ).update(proxima_tentativa=agora + contexto.RESERVA_DA_TENTATIVA)
    return bool(reservado)


def processar(envio_id, *, agora=None, trocas=None):
    """Tenta enviar um `EnvioEmail` pendente e vencido. Devolve a situação final."""
    agora = agora or contexto.agora()
    envio = EnvioEmail.objects.select_related("nfse").get(pk=envio_id)
    if not _reservar(envio, agora):
        return envio.situacao
    envio.refresh_from_db()
    empresa = contexto.empresa_atual()
    configuracao = ConfiguracaoEmail.obter()
    try:
        provedor = fabrica.criar_provedor(configuracao, trocas)
        if envio.tipo == T.ALERTA_CERTIFICADO or envio.nfse is None:
            mensagem = MensagemEmail(
                remetente=configuracao.remetente_email,
                nome_remetente=configuracao.remetente_nome,
                destinatarios=list(envio.destinatarios),
                copias=list(envio.copias),
                assunto=envio.assunto,
                texto=envio.corpo_avulso,
            )
        else:
            efetiva = configuracao_efetiva(configuracao, envio.nfse)
            assunto, texto, corpo_html = renderizar(efetiva, envio.nfse, empresa)
            if envio.tipo == T.CANCELAMENTO:
                assunto = f"CANCELADA — {assunto}"
                texto = "Esta nota foi CANCELADA.\n\n" + texto
                corpo_html = corpo_html.replace(
                    "<body>", "<body><p><b>Esta nota foi CANCELADA.</b></p>", 1
                )
            anexos, nomes = _anexos(efetiva, envio.nfse, empresa)
            mensagem = MensagemEmail(
                remetente=configuracao.remetente_email,
                nome_remetente=configuracao.remetente_nome,
                destinatarios=list(envio.destinatarios),
                copias=list(envio.copias),
                assunto=assunto,
                texto=texto,
                html=corpo_html,
                anexos=anexos,
            )
            envio.anexos = nomes
        envio.assunto = mensagem.assunto[:300]
        provedor.enviar(mensagem)
    except emissao.ErroDeEmissao as erro:
        _registrar_falha(envio, ErroDeEnvio(str(erro), detalhe="anexo indisponível"), agora)
    except ErroDeEnvio as erro:
        _registrar_falha(envio, erro, agora)
    else:
        envio.situacao = S.ENVIADO
        envio.enviado_em = agora
        envio.tentativas += 1
        envio.proxima_tentativa = None
        envio.erro = envio.erro_tecnico = ""
        envio.save()
    return envio.situacao


def _registrar_falha(envio, erro, agora):
    envio.tentativas += 1
    envio.erro = erro.mensagem
    envio.erro_tecnico = erro.detalhe
    if erro.temporario and envio.tentativas < envio.max_tentativas:
        envio.situacao = S.PENDENTE
        envio.proxima_tentativa = agora + contexto.espera_apos(envio.tentativas)
    else:
        envio.situacao = S.FALHOU
        envio.proxima_tentativa = None
    envio.save()


def pendentes_vencidos(agora=None):
    """Ids dos envios pendentes cuja hora de tentar já chegou."""
    agora = agora or contexto.agora()
    return list(
        EnvioEmail.objects.filter(situacao=S.PENDENTE, proxima_tentativa__lte=agora).values_list(
            "pk", flat=True
        )
    )


def reenviar(envio, *, usuario, agora=None):
    """Novo envio (tipo "reenvio") com os mesmos destinatários de um envio anterior."""
    novo = solicitar(
        envio.nfse,
        T.REENVIO,
        usuario=usuario,
        destinatarios=envio.destinatarios or None,
        agora=agora,
    )
    auditoria.registrar(
        LogAuditoria.Acao.EMAIL_REENVIADO,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo=f"nfse:{envio.nfse_id}",
        detalhes={"envio": novo.pk},
    )
    return novo


# --- Teste e alerta ------------------------------------------------------------------------


def enviar_teste(destino, *, usuario, trocas=None, agora=None):
    """Envia na hora um e-mail de teste e registra o resultado. Devolve o `EnvioEmail`."""
    agora = agora or contexto.agora()
    configuracao = ConfiguracaoEmail.obter()
    envio = EnvioEmail.objects.create(
        tipo=T.TESTE,
        provedor=configuracao.provedor,
        destinatarios=[destino],
        assunto="Teste de envio de e-mail do freenfse",
        proxima_tentativa=agora,
        **_quem(usuario),
    )
    try:
        provedor = fabrica.criar_provedor(configuracao, trocas)
        provedor.enviar(
            MensagemEmail(
                remetente=configuracao.remetente_email,
                nome_remetente=configuracao.remetente_nome,
                destinatarios=[destino],
                assunto=envio.assunto,
                texto="Se você recebeu esta mensagem, o envio de e-mail está funcionando.",
            )
        )
    except ErroDeEnvio as erro:
        envio.tentativas = 1
        envio.situacao = S.FALHOU
        envio.erro, envio.erro_tecnico = erro.mensagem, erro.detalhe
        envio.proxima_tentativa = None
    else:
        envio.tentativas = 1
        envio.situacao = S.ENVIADO
        envio.enviado_em = agora
        envio.proxima_tentativa = None
    envio.save()
    auditoria.registrar(
        LogAuditoria.Acao.EMAIL_TESTE_ENVIADO,
        usuario=usuario,
        empresa=contexto.empresa_atual(),
        alvo="email-teste",
        detalhes={"situacao": envio.situacao},
    )
    return envio


def destinatarios_do_alerta(configuracao, empresa):
    """Quem recebe o alerta de certificado: lista da configuração ou os administradores ativos."""
    if configuracao.emails_alerta:
        return list(configuracao.emails_alerta)
    vinculos = VinculoUsuarioEmpresa.objects.filter(
        empresa=empresa, perfil=Perfil.ADMINISTRADOR, ativo=True, usuario__is_active=True
    ).select_related("usuario")
    return sorted({v.usuario.email for v in vinculos if v.usuario.email})


def registrar_aviso_avulso(*, tipo, destinatarios, assunto, texto, chave_idempotencia, agora=None):
    """Cria um e-mail do sistema sem nota, uma única vez por `chave_idempotencia`.

    Devolve `None` se o e-mail da empresa está desligado ou não há para quem enviar: o aviso
    continua visível na tela de quem o originou. O envio é feito pela fila periódica.
    """
    agora = agora or contexto.agora()
    configuracao = ConfiguracaoEmail.obter()
    para = sorted({e for e in destinatarios if e})
    if configuracao.provedor == ConfiguracaoEmail.Provedor.NENHUM or not para:
        return None
    existente = EnvioEmail.objects.filter(chave_idempotencia=chave_idempotencia).first()
    if existente:
        return existente
    return EnvioEmail.objects.create(
        tipo=tipo,
        provedor=configuracao.provedor,
        destinatarios=para,
        assunto=_linha_unica(assunto)[:300],
        corpo_avulso=texto,
        chave_idempotencia=chave_idempotencia,
        proxima_tentativa=agora,
    )


def registrar_alerta_de_certificado(*, empresa, faixa, dias_restantes, impressao, agora=None):
    """Cria o e-mail de alerta de vencimento (uma vez por certificado e faixa)."""
    agora = agora or contexto.agora()
    configuracao = ConfiguracaoEmail.obter()
    if configuracao.provedor == ConfiguracaoEmail.Provedor.NENHUM:
        return None
    para = destinatarios_do_alerta(configuracao, empresa)
    if not para:
        return None
    if dias_restantes < 0 or faixa == 0:
        assunto = f"O certificado digital de {empresa.razao_social} venceu"
        texto = "O certificado digital A1 venceu. Sem ele não é possível emitir notas."
    else:
        assunto = (
            f"O certificado digital de {empresa.razao_social} vence em {dias_restantes} dia(s)"
        )
        texto = (
            f"O certificado digital A1 da empresa vence em {dias_restantes} dia(s). Envie o novo "
            "certificado em Configuração fiscal › Certificado A1 antes disso."
        )
    chave = f"alerta:{impressao[:16]}:{int(faixa)}"
    existente = EnvioEmail.objects.filter(chave_idempotencia=chave).first()
    if existente:
        return existente
    return EnvioEmail.objects.create(
        tipo=T.ALERTA_CERTIFICADO,
        provedor=configuracao.provedor,
        destinatarios=para,
        assunto=_linha_unica(assunto),
        corpo_avulso=texto,
        chave_idempotencia=chave,
        proxima_tentativa=agora,
    )
