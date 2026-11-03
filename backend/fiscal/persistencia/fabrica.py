"""Monta as peças de persistência que `criar_servico_nfse` exige, para a empresa ativa."""

from dataclasses import dataclass

from freedfe.distribuicao.estado import relogio_utc

from fiscal.persistencia.auditoria import AuditoriaPostgres
from fiscal.persistencia.cache import CacheParametrosPostgres
from fiscal.persistencia.estado_emissao import EstadoEmissaoPostgres
from fiscal.persistencia.evidencias import ArmazenamentoEvidenciasPostgres
from fiscal.persistencia.nsu import EstadoSequenciaNsuPostgres
from fiscal.persistencia.repositorio import RepositorioDocumentosPostgres
from fiscal.persistencia.trava import TravaPostgres

# Quanto uma emissão espera outra da mesma empresa terminar antes de desistir (e ser
# reagendada pelo Celery). Emissões da mesma empresa se enfileiram em vez de falhar.
ESPERA_DA_TRAVA_DE_EMISSAO = 60.0


@dataclass
class Persistencia:
    """Conjunto de dependências de persistência da freedfe, no schema da empresa ativa."""

    repositorio: RepositorioDocumentosPostgres
    estado_emissao: EstadoEmissaoPostgres
    travas: object
    estado_nsu: object
    cache_parametros: CacheParametrosPostgres
    evidencias: ArmazenamentoEvidenciasPostgres
    auditoria: AuditoriaPostgres


def criar_persistencia(
    *,
    interessado,
    nfse_id=None,
    relogio=relogio_utc,
    espera_da_trava=ESPERA_DA_TRAVA_DE_EMISSAO,
    pausa=None,
):
    """Persistência da empresa ativa (a conexão já aponta para o schema dela).

    Args:
        interessado: CNPJ da empresa (dono do repositório).
        nfse_id: nota a que as DPS reservadas nesta operação pertencem.
        relogio: relógio dos carimbos e do cache.
        espera_da_trava: segundos que a trava espera antes de falhar.
        pausa: espera entre as tentativas da trava (nos testes, sem dormir de verdade).

    """
    opcoes_da_trava = {"espera_segundos": espera_da_trava}
    if pausa is not None:
        opcoes_da_trava["pausa"] = pausa
    return Persistencia(
        repositorio=RepositorioDocumentosPostgres(interessado),
        estado_emissao=EstadoEmissaoPostgres(relogio, nfse_id=nfse_id),
        travas=lambda recurso: TravaPostgres(recurso, **opcoes_da_trava),
        estado_nsu=lambda recurso: EstadoSequenciaNsuPostgres(recurso, relogio),
        cache_parametros=CacheParametrosPostgres(relogio),
        evidencias=ArmazenamentoEvidenciasPostgres(),
        auditoria=AuditoriaPostgres(),
    )
