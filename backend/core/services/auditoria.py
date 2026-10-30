"""Registro na trilha de auditoria."""

from allauth.core.internal.httpkit import get_client_ip

from core.models import LogAuditoria


def ip_do_pedido(request):
    """IP do cliente, respeitando o cabeçalho confiável configurado (`IP_CABECALHO_CONFIAVEL`)."""
    if request is None:
        return None
    try:
        return get_client_ip(request) or None
    except Exception:  # noqa: BLE001 - nunca impedir a operação por falha ao ler o IP
        return None


def registrar(acao, *, request=None, usuario=None, empresa=None, alvo="", detalhes=None):
    """Grava uma linha de auditoria.

    Sem `usuario`/`empresa` explícitos, usa os da requisição (`request.user` e
    `request.empresa`, definido pelo middleware de empresa).
    """
    if usuario is None and request is not None:
        candidato = getattr(request, "user", None)
        usuario = candidato if candidato is not None and candidato.is_authenticated else None
    if empresa is None and request is not None:
        empresa = getattr(request, "empresa", None)
    return LogAuditoria.objects.create(
        usuario=usuario,
        usuario_snapshot=usuario.email if usuario else "",
        empresa=empresa,
        empresa_snapshot=empresa.cnpj if empresa else "",
        acao=acao,
        alvo=str(alvo)[:120],
        ip=ip_do_pedido(request),
        master=bool(usuario and usuario.is_master),
        detalhes=detalhes or {},
    )
