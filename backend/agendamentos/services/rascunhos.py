"""Rascunhos de NFS-e: aprovação (individual e em lote) e descarte com motivo.

Aprovar é pedir a emissão: cada nota passa **pelo mesmo caminho** da emissão manual da Fase 3
(`emissao.solicitar_emissao`, depois a fila). O lote nunca para numa nota recusada: devolve o
resultado de cada item. Rascunho não é emitido nem apagado sozinho (D12).
"""

from core.models import LogAuditoria
from core.services import auditoria
from fiscal.models import Nfse, TransicaoInvalida
from fiscal.services import emissao
from fiscal.services.nfse_estados import transicionar

S = Nfse.Situacao
LIMITE_DO_LOTE = 100
TAMANHO_MINIMO_DO_MOTIVO = 5


class ErroDeRascunho(Exception):
    """Pedido inválido; `erros` mapeia o campo à mensagem para o usuário."""

    def __init__(self, erros):
        """Aceita um dicionário campo → mensagem ou uma mensagem única (campo `geral`)."""
        if isinstance(erros, str):
            erros = {"geral": erros}
        super().__init__("; ".join(erros.values()))
        self.erros = erros


def descartar(nfse, *, motivo, usuario, empresa, request=None):
    """Descarta um rascunho (situação final), guardando o motivo no histórico da nota."""
    motivo = (motivo or "").strip()
    if len(motivo) < TAMANHO_MINIMO_DO_MOTIVO:
        raise ErroDeRascunho({"motivo": "Explique por que o rascunho será descartado."})
    try:
        transicionar(nfse, S.DESCARTADA, motivo=f"Descartado: {motivo}", usuario=usuario)
    except TransicaoInvalida:
        raise ErroDeRascunho("Só um rascunho pode ser descartado.") from None
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_DESCARTADA,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"motivo": motivo[:200]},
    )
    return nfse


def _recusada(nfse_id, codigo, mensagem):
    return {"id": nfse_id, "ok": False, "codigo": codigo, "mensagem": mensagem}


def aprovar_em_lote(ids, *, usuario, empresa, permissoes, request=None):
    """Pede a emissão de cada rascunho e devolve o resultado por item (na ordem pedida).

    Item aceito: `{"id", "ok": True, "situacao": "enviando"}` (o envio à Sefin é assíncrono; a
    tela acompanha). Item recusado: `{"id", "ok": False, "codigo", "mensagem"}`. Quem chama
    enfileira a emissão dos aceitos.
    """
    ids = list(dict.fromkeys(ids))  # sem repetidos, mantendo a ordem
    if not ids:
        raise ErroDeRascunho({"ids": "Escolha pelo menos um rascunho."})
    if len(ids) > LIMITE_DO_LOTE:
        raise ErroDeRascunho({"ids": f"Aprove no máximo {LIMITE_DO_LOTE} rascunhos por vez."})
    notas = Nfse.objects.in_bulk(ids)
    resultados = []
    for nfse_id in ids:
        resultados.append(
            _aprovar(notas.get(nfse_id), nfse_id, usuario, empresa, permissoes, request)
        )
    aceitas = sum(r["ok"] for r in resultados)
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_LOTE_APROVADO,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo="lote",
        detalhes={"aceitas": aceitas, "recusadas": len(resultados) - aceitas},
    )
    return resultados


def _aprovar(nfse, nfse_id, usuario, empresa, permissoes, request):
    if nfse is None:
        return _recusada(nfse_id, "nao_encontrada", "Rascunho não encontrado.")
    if nfse.situacao != S.RASCUNHO:
        return _recusada(
            nfse_id, "nao_e_rascunho", f"A nota está {nfse.get_situacao_display().lower()}."
        )
    if nfse.substitui_id and "nfse.substituir" not in permissoes:
        return _recusada(
            nfse_id,
            "permissao_negada",
            "Emitir uma nota substituta exige a permissão de substituir notas.",
        )
    try:
        emissao.solicitar_emissao(nfse, usuario=usuario, request=request, empresa=empresa)
    except emissao.BloqueioDeEmissao as erro:
        return _recusada(nfse_id, "empresa_nao_pronta", str(erro))
    except (emissao.ErroDeEmissao, TransicaoInvalida) as erro:
        return _recusada(nfse_id, "operacao_recusada", str(erro))
    return {
        "id": nfse_id,
        "ok": True,
        "situacao": nfse.situacao,
        "mensagem": "Enviada para emissão.",
    }
