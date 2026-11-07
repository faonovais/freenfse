"""Tabelas oficiais da NFS-e (NT 009 e calculadora do IBS/CBS), lidas de arquivos versionados.

Nenhum módulo daqui faz consulta de rede nem acessa o banco: os dados vêm de `dados/*.json`, que
os comandos `importar_anexos_rtc` e `atualizar_classificacao_tributaria` regravam a partir das
fontes oficiais. A origem, a data e o SHA-256 de cada arquivo estão em `dados/LEIAME.md`.
"""
