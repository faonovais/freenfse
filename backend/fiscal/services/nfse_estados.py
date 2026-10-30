"""Máquina de estados da NFS-e: a única porta para mudar a situação de uma nota.

Cada mudança confere a tabela de transições, é gravada com travamento da linha (duas ações
simultâneas não passam por cima uma da outra) e deixa histórico (`TransicaoNfse`). Transição
fora da tabela levanta `TransicaoInvalida`: o sistema prefere recusar a deixar uma nota num
estado impossível.
"""

from django.db import transaction

from fiscal.models import Nfse, TransicaoInvalida, TransicaoNfse

S = Nfse.Situacao

TRANSICOES = {
    S.RASCUNHO: {S.ENVIANDO},
    # `ENVIANDO → RASCUNHO`: a DPS foi recusada localmente (dado inválido) e nada foi enviado.
    S.ENVIANDO: {S.AUTORIZADA, S.REJEITADA, S.INCERTA, S.RASCUNHO},
    # `INCERTA → ENVIANDO` só acontece pela retomada, que consulta a Sefin antes de enviar.
    S.INCERTA: {S.AUTORIZADA, S.ENVIANDO},
    # `REJEITADA → ENVIANDO`: corrigida e reenviada com o mesmo número de DPS.
    S.REJEITADA: {S.ENVIANDO},
    S.AUTORIZADA: {S.CANCELADA, S.SUBSTITUIDA},
    S.CANCELADA: set(),
    S.SUBSTITUIDA: set(),
}


def pode_transicionar(de, para):
    """Diz se a tabela permite `de → para`."""
    return Nfse.Situacao(para) in TRANSICOES[Nfse.Situacao(de)]


def transicionar(nfse, nova, *, motivo="", usuario=None, **campos):
    """Muda a situação da nota (e grava `campos` junto), registrando o histórico.

    A linha é relida com `FOR UPDATE`: vale a situação **atual do banco**, não a da instância
    que o chamador tem na mão. Levanta `TransicaoInvalida` se a tabela não permitir.
    """
    nova = Nfse.Situacao(nova)
    with transaction.atomic():
        atual = Nfse.objects.select_for_update().get(pk=nfse.pk)
        if nova not in TRANSICOES[atual.situacao]:
            raise TransicaoInvalida(
                f"Esta nota está '{atual.get_situacao_display()}' e não pode passar para "
                f"'{nova.label}'."
            )
        anterior = atual.situacao
        for nome, valor in campos.items():
            setattr(atual, nome, valor)
        atual.situacao = nova
        atual.__dict__["_transicao_autorizada"] = True
        atual.save()
        TransicaoNfse.objects.create(
            nfse=atual,
            de=anterior,
            para=nova,
            motivo=motivo[:255],
            usuario_email=getattr(usuario, "email", "") if usuario else "",
        )
    nfse.refresh_from_db()
    nfse._situacao_gravada = nfse.situacao
    return nfse
