"""Persistência da freedfe em PostgreSQL, por schema de empresa.

A biblioteca define contratos (estado das emissões, trava, NSU, evidências, repositório de
documentos, cache e auditoria) e a aplicação os implementa. Todas as tabelas vivem no schema
da empresa (django-tenants): nenhuma consulta daqui enxerga dados de outra empresa.

Regra de ouro da emissão: cada operação de estado grava e confirma na hora (autocommit). Nada
disto roda dentro de uma transação aberta pelo chamador, senão o `ENVIADA` gravado antes do
`POST` à Sefin não sobreviveria a uma queda do processo.
"""
