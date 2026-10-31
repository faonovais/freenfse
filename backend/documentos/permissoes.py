"""Permissões do app documentos (registradas no catálogo central em `core.permissoes`)."""

from core.permissoes import Perfil, registrar_permissao

registrar_permissao(
    "documentos.consultar",
    "Consultar o histórico de envios de e-mail e Drive e as exportações",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO, Perfil.CONSULTA],
)
registrar_permissao(
    "documentos.exportar",
    "Baixar notas em lote (ZIP com XML, PDF e planilha)",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO],
)
registrar_permissao(
    "documentos.enviar",
    "Enviar e reenviar notas por e-mail e ao Google Drive",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO],
)
