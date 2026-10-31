"""Avisos dos agendamentos: e-mail (pela Fase 4, conforme a configuração) e quem recebe.

Todo aviso também fica visível na tela (histórico de execuções, situação do agendamento): o
e-mail é um reforço, e some em silêncio se a empresa ainda não configurou o envio.
"""

from core.models import VinculoUsuarioEmpresa
from core.permissoes import Perfil
from documentos.models import EnvioEmail
from documentos.services import envio_email

T = EnvioEmail.Tipo


def administradores(empresa):
    """E-mails dos Administradores ativos da empresa."""
    vinculos = VinculoUsuarioEmpresa.objects.filter(
        empresa=empresa, perfil=Perfil.ADMINISTRADOR, ativo=True, usuario__is_active=True
    ).select_related("usuario")
    return {v.usuario.email for v in vinculos if v.usuario.email}


def _enviar(*, agendamento, empresa, chave, assunto, texto, destinatarios, agora, tipo=None):
    return envio_email.registrar_aviso_avulso(
        tipo=tipo or T.AVISO_AGENDAMENTO,
        destinatarios=destinatarios,
        assunto=assunto,
        texto=f"Empresa: {empresa.razao_social}\nAgendamento: {agendamento.nome}\n\n{texto}",
        chave_idempotencia=f"agendamento:{agendamento.pk}:{chave}"[:80],
        agora=agora,
    )


def avisar_rascunho_gerado(agendamento, execucao, *, empresa, agora):
    """Avisa o responsável que há um rascunho esperando a aprovação dele."""
    texto = (
        f"O agendamento gerou o rascunho de {execucao.data_execucao:%d/%m/%Y}. Nada foi emitido: "
        "confira os dados e aprove em Agendamentos › Rascunhos."
    )
    return _enviar(
        agendamento=agendamento,
        empresa=empresa,
        chave=f"{execucao.data_execucao}:gerado",
        assunto=f"Rascunho de NFS-e para aprovar: {agendamento.nome}",
        texto=texto,
        destinatarios={agendamento.responsavel_email},
        agora=agora,
    )


def avisar_falha(agendamento, execucao, *, empresa, agora):
    """Avisa o responsável e os administradores que a geração do rascunho falhou."""
    texto = (
        f"Não foi possível gerar o rascunho de {execucao.data_execucao:%d/%m/%Y}.\n\n"
        f"Motivo: {execucao.erro}\n\n"
        "Esta data não conta como execução realizada. O agendamento tenta de novo na próxima "
        "data prevista; corrija o problema antes disso. Para gerar agora, use o modelo em "
        "Agendamentos › Modelos."
    )
    return _enviar(
        agendamento=agendamento,
        empresa=empresa,
        chave=f"{execucao.data_execucao}:falha",
        assunto=f"O agendamento “{agendamento.nome}” não conseguiu gerar o rascunho",
        texto=texto,
        destinatarios={agendamento.responsavel_email} | administradores(empresa),
        agora=agora,
    )


def avisar_suspensao(agendamento, execucao, *, empresa, agora):
    """Avisa os administradores que o agendamento foi suspenso (responsável sem acesso)."""
    texto = (
        f"O agendamento foi SUSPENSO e não gerou o rascunho de "
        f"{execucao.data_execucao:%d/%m/%Y}.\n\n"
        f"Motivo: {agendamento.motivo_situacao}\n\n"
        "Troque o responsável (ou devolva o acesso a ele) e reative o agendamento em "
        "Agendamentos. Datas perdidas durante a suspensão não são geradas depois."
    )
    return _enviar(
        agendamento=agendamento,
        empresa=empresa,
        chave=f"{execucao.data_execucao}:suspenso",
        assunto=f"Agendamento suspenso: {agendamento.nome}",
        texto=texto,
        destinatarios=administradores(empresa),
        agora=agora,
    )


def avisar_execucao_perdida(agendamento, execucao, *, empresa, agora):
    """Avisa que o sistema ficou fora do ar e pulou datas (o responsável decide se gera à mão)."""
    texto = (
        f"{execucao.erro}\n\n"
        "Se a nota ainda for necessária, gere o rascunho agora pelo modelo "
        "(Agendamentos › Modelos › Gerar rascunho)."
    )
    return _enviar(
        agendamento=agendamento,
        empresa=empresa,
        chave=f"{execucao.data_execucao}:perdida",
        assunto=f"Agendamento com data não executada: {agendamento.nome}",
        texto=texto,
        destinatarios={agendamento.responsavel_email} | administradores(empresa),
        agora=agora,
    )


def avisar_rascunhos_pendentes(*, empresa, responsavel_id, responsavel_email, itens, dia, agora):
    """Alerta diário: quantos rascunhos agendados esperam aprovação (um e-mail por responsável)."""
    linhas = "\n".join(f"- {nome}: {quantidade}" for nome, quantidade in sorted(itens.items()))
    total = sum(itens.values())
    texto = (
        f"Empresa: {empresa.razao_social}\n\n"
        f"Há {total} rascunho(s) de NFS-e gerado(s) por agendamento esperando a sua aprovação:\n"
        f"{linhas}\n\n"
        "Aprove ou descarte em Agendamentos › Rascunhos. Nenhum rascunho é emitido nem apagado "
        "sozinho."
    )
    return envio_email.registrar_aviso_avulso(
        tipo=T.RASCUNHOS_PENDENTES,
        destinatarios={responsavel_email},
        assunto=f"{total} rascunho(s) de NFS-e para aprovar",
        texto=texto,
        chave_idempotencia=f"rascunhos:{responsavel_id}:{dia}"[:80],
        agora=agora,
    )
