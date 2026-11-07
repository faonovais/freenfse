"""Destinatário do serviço na nota (issue #33, ADR 0011).

Quando o destinatário **não é o próprio tomador** (`indDest = 1`), a DPS precisa dizer quem ele é
(grupo `dest`), e as regras E0243/E0919 do Anexo VI dependem dos dados dele. O destinatário é uma
`Pessoa` do cadastro da mesma empresa, escolhida:

1. na **nota** (o que o usuário escolheu naquela nota);
2. no **modelo** de NFS-e (vazio = não define; a nota ainda pode escolher).

Só vale com o grupo de IBS/CBS na DPS **e** `indDest = 1`; com `indDest = 0` (ou sem grupo) é
descartado. Como o tomador, o destinatário vai na nota como **cópia** (snapshot) dos dados do
cadastro no momento em que o rascunho é gravado.
"""

from cadastros.models import Pessoa

ORIGEM_NOTA, ORIGEM_MODELO = "nota", "modelo"
ROTULO_DA_ORIGEM = {ORIGEM_NOTA: "escolhido nesta nota", ORIGEM_MODELO: "do modelo"}
TAMANHO_MAXIMO_DO_NOME = 150  # xNome do destinatário na DPS (a biblioteca recusa mais que isto)


def como_id(valor):
    """O id de pessoa a partir do que a entrada trouxe (`''`, `None` e lixo viram `None`)."""
    if isinstance(valor, bool) or valor in (None, ""):
        return None
    try:
        return int(valor)
    except TypeError, ValueError:
        return None


def escolhido(nota, modelo):
    """`(id, origem)` do destinatário escolhido (nota > modelo); `(None, None)` se ninguém."""
    for origem, bruto in ((ORIGEM_NOTA, nota), (ORIGEM_MODELO, modelo)):
        pessoa_id = como_id(bruto)
        if pessoa_id is not None:
            return pessoa_id, origem
    return None, None


def resolver(nota, modelo, snapshot_da_pessoa):
    """Procura e copia o destinatário escolhido; `(info, erro)`.

    `info` é `{"pessoa": id, "origem": "nota"|"modelo", "dados": {...cópia da pessoa...}}` ou
    `None` (ninguém escolheu). `erro` é a mensagem para o usuário quando a escolha não serve.
    `snapshot_da_pessoa` copia os campos da pessoa (o mesmo do tomador).
    """
    pessoa_id, origem = escolhido(nota, modelo)
    if pessoa_id is None:
        return None, None
    pessoa = Pessoa.objects.filter(pk=pessoa_id, ativo=True).first()
    if pessoa is None:
        return None, "Escolha um destinatário ativo do cadastro de pessoas."
    if len(pessoa.nome) > TAMANHO_MAXIMO_DO_NOME:
        return None, (
            f"O nome de “{pessoa.nome[:40]}…” passa de {TAMANHO_MAXIMO_DO_NOME} caracteres, o "
            "limite do destinatário na DPS. Encurte o nome no cadastro de pessoas."
        )
    return {"pessoa": pessoa.pk, "origem": origem, "dados": snapshot_da_pessoa(pessoa)}, None


MENSAGEM_DE_DESTINATARIO_FALTANDO = (
    "O destinatário é outra pessoa (não o próprio tomador), então a nota precisa dizer quem ele "
    "é. Escolha o destinatário no cadastro de pessoas (ou, se for o próprio tomador, mude para "
    "“o destinatário é o próprio tomador”)."
)
