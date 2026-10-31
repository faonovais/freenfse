"""Permissões do app agendamentos (registradas no catálogo central em `core.permissoes`).

Aprovar, editar e descartar rascunhos usa `nfse.emitir`/`nfse.consultar`: emitir é sempre um ato de
quem tem a permissão de emitir (D12).
"""

from core.permissoes import Perfil, registrar_permissao

registrar_permissao(
    "agendamento.consultar",
    "Consultar modelos de NFS-e, agendamentos e o histórico de execuções",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO, Perfil.CONSULTA],
)
registrar_permissao(
    "agendamento.editar",
    "Criar e alterar modelos de NFS-e e agendamentos",
    perfis=[Perfil.EMISSOR],
)
