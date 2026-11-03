"""Estado da sequência de NSU (distribuição do ADN) em PostgreSQL."""

import copy

from freedfe.distribuicao.estado import BLOQUEIO_SEGUNDOS, EstadoSequenciaNsu, relogio_utc

from fiscal.persistencia.modelos import EstadoNsuFiscal


class EstadoSequenciaNsuPostgres(EstadoSequenciaNsu):
    """Uma linha por recurso (`nsu_nfse`, `nsu_nfse_<cnpj>`) no schema da empresa.

    Quem consome a sequência deve segurar a `Trava` do mesmo recurso durante todo o ciclo
    ler-alterar-salvar (a biblioteca já faz isso).
    """

    def __init__(self, recurso, relogio=relogio_utc, bloqueio_segundos=BLOQUEIO_SEGUNDOS):
        """Lê o estado do recurso já na construção, como a biblioteca exige."""
        self.recurso = recurso  # precisa existir antes de `super().__init__` (lê o estado)
        super().__init__(relogio, bloqueio_segundos)

    def _ler_dados(self):
        linha = EstadoNsuFiscal.objects.filter(recurso=self.recurso).first()
        return copy.deepcopy(linha.dados) if linha else None

    def _gravar_dados(self, dados):
        EstadoNsuFiscal.objects.update_or_create(
            recurso=self.recurso, defaults={"dados": copy.deepcopy(dados)}
        )
