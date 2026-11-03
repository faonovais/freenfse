"""Cache dos parâmetros municipais (convênio, alíquotas, retenções) em PostgreSQL."""

import copy
import datetime as dt

from freedfe.nfse.parametros import TTL_PADRAO, CacheParametros

from fiscal.persistencia.modelos import CacheParametroFiscal


class CacheParametrosPostgres(CacheParametros):
    """Uma linha por município e consulta; o TTL e a regra de uso ficam na biblioteca."""

    def __init__(self, relogio=None, ttl: dt.timedelta = TTL_PADRAO):
        """Usa o relógio UTC da biblioteca quando `relogio` não é informado."""
        if relogio is None:
            super().__init__(ttl=ttl)
        else:
            super().__init__(relogio, ttl)

    def _ler(self, municipio, nome):
        linha = CacheParametroFiscal.objects.filter(municipio=municipio, nome=nome).first()
        if linha is None:
            return None
        return linha.consultado_em, copy.deepcopy(linha.dados)

    def _gravar(self, municipio, nome, momento, dados):
        CacheParametroFiscal.objects.update_or_create(
            municipio=municipio,
            nome=nome,
            defaults={"consultado_em": momento, "dados": copy.deepcopy(dados)},
        )
