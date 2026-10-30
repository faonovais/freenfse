"""Estado das emissões em PostgreSQL: numeração atômica e máquina de estados da DPS.

Cumpre o contrato `freedfe.nfse.estado_emissao.EstadoEmissao` (verificado pela suíte de
contrato da própria biblioteca, adaptada em `fiscal/tests/persistencia/`).

Dois níveis de proteção contra número repetido, que é o pior erro fiscal possível aqui:

1. `reservar_proximo` trava a linha da série (`SELECT ... FOR UPDATE`) e só então calcula
   `max(numero) + 1`: duas transações na mesma série se enfileiram, mesmo sem a trava de
   emissão;
2. `UNIQUE (emitente, serie, numero)` no banco: se alguém contornar o item 1, a segunda
   gravação falha em vez de duplicar a numeração.

Cada método confirma o que gravou na hora (autocommit). Em especial o `ENVIADA`, gravado antes
do `POST` à Sefin, precisa sobreviver a uma queda do processo: é ele que faz o próximo passo
ser "conferir na Sefin", e não "enviar de novo".
"""

from collections.abc import Callable

from django.db import IntegrityError, transaction
from django.db.models import Max
from freedfe.distribuicao.estado import Relogio, relogio_utc
from freedfe.excecoes import ValidacaoErro
from freedfe.nfse.estado_emissao import EstadoEmissao, RegistroEmissao, SituacaoEmissao
from freedfe.validadores import exigir_id_dps

from fiscal.persistencia.modelos import EmissaoDps, SerieDps

_CAMPOS_DO_REGISTRO = (
    "chave",
    "erros",
    "motivo",
    "tentativas",
    "caminho_dps",
    "caminho_resposta",
    "ts_reserva",
    "ts_envio",
    "ts_resposta",
)


def _emitente_do_id(id_dps):
    """CNPJ/CPF do emitente: posições 12 a 25 do Id (`DPS` + município + tipo + documento…)."""
    return id_dps[11:25]


def _registro(linha):
    """Devolve o registro da biblioteca correspondente à linha do banco (cópia solta)."""
    return RegistroEmissao(
        id_dps=linha.id_dps,
        serie=linha.serie,
        numero=linha.numero,
        situacao=SituacaoEmissao(linha.situacao),
        chave=linha.chave,
        erros=list(linha.erros or []),
        motivo=linha.motivo,
        tentativas=linha.tentativas,
        caminho_dps=linha.caminho_dps,
        caminho_resposta=linha.caminho_resposta,
        ts_reserva=linha.ts_reserva,
        ts_envio=linha.ts_envio,
        ts_resposta=linha.ts_resposta,
    )


def _copiar_para_linha(registro, linha):
    linha.situacao = registro.situacao.value
    for campo in _CAMPOS_DO_REGISTRO:
        setattr(linha, campo, getattr(registro, campo))


class EstadoEmissaoPostgres(EstadoEmissao):
    """Estado das emissões no schema da empresa ativa.

    Args:
        relogio: relógio dos carimbos `ts_*` (injetável nos testes).
        nfse_id: nota do freenfse a que as DPS reservadas por esta instância pertencem. A
            ligação é gravada na própria reserva, sem janela em que a DPS exista sem dono.

    """

    def __init__(self, relogio: Relogio = relogio_utc, nfse_id: int | None = None):
        """Guarda o relógio dos carimbos e a nota dona das reservas."""
        super().__init__(relogio)
        self._nfse_id = nfse_id

    # -- consulta ----------------------------------------------------------------------

    def obter(self, id_dps: str) -> RegistroEmissao | None:
        """Registro da DPS, lido do banco a cada chamada."""
        linha = EmissaoDps.objects.filter(id_dps=id_dps).first()
        return _registro(linha) if linha else None

    def listar(self, situacao: SituacaoEmissao | str | None = None) -> list[RegistroEmissao]:
        """Registros (opcionalmente de uma situação) por série, número e Id."""
        consulta = EmissaoDps.objects.order_by("serie", "numero", "id_dps")
        if situacao is not None:
            consulta = consulta.filter(situacao=SituacaoEmissao(situacao).value)
        return [_registro(linha) for linha in consulta]

    def proximo_numero(self, serie: int) -> int:
        """Maior número usado na série + 1. Só consulta; não reserva."""
        maior = EmissaoDps.objects.filter(serie=int(serie)).aggregate(m=Max("numero"))["m"]
        return (maior or 0) + 1

    # -- reserva -----------------------------------------------------------------------

    def reservar(self, id_dps: str, serie: int, numero: int) -> RegistroEmissao:
        """Cria (ou reabre, após rejeição) a DPS como `PENDENTE`."""
        id_dps = exigir_id_dps(id_dps)
        with transaction.atomic():
            linha = EmissaoDps.objects.select_for_update().filter(id_dps=id_dps).first()
            self._validar_reserva(_registro(linha) if linha else None)
            registro = self._registro_reservado(
                _registro(linha) if linha else None, id_dps, int(serie), int(numero)
            )
            if linha is None:
                linha = EmissaoDps(
                    id_dps=id_dps,
                    emitente=_emitente_do_id(id_dps),
                    serie=int(serie),
                    numero=int(numero),
                    nfse_id=self._nfse_id,
                )
            elif linha.nfse_id is None:
                linha.nfse_id = self._nfse_id
            _copiar_para_linha(registro, linha)
            try:
                with transaction.atomic():
                    linha.save()
            except IntegrityError as erro:
                raise ValidacaoErro(
                    f"A numeração {serie}/{numero} já está reservada para este emitente."
                ) from erro
            return registro

    def garantir(self, id_dps: str, serie: int, numero: int) -> RegistroEmissao:
        """Registro existente ou um novo `PENDENTE`."""
        existente = self.obter(id_dps)
        if existente is not None:
            return existente
        return self.reservar(id_dps, serie, numero)

    def reservar_proximo(self, serie: int, montar_id: Callable[[int], str]) -> RegistroEmissao:
        """Reserva o próximo número da série de forma atômica.

        A linha da série é travada (`FOR UPDATE`) antes de calcular o número; quem chega
        depois espera o commit de quem chegou antes e vê a reserva dele.
        """
        serie = int(serie)
        with transaction.atomic():
            SerieDps.objects.bulk_create([SerieDps(serie=serie)], ignore_conflicts=True)
            SerieDps.objects.select_for_update().get(serie=serie)
            numero = self.proximo_numero(serie)
            return self.reservar(montar_id(numero), serie, numero)

    def descartar(self, id_dps: str) -> None:
        """Remove a reserva `PENDENTE` nunca enviada."""
        with transaction.atomic():
            linha = EmissaoDps.objects.select_for_update().filter(id_dps=id_dps).first()
            self._validar_descarte(id_dps, _registro(linha) if linha else None)
            linha.delete()

    # -- transição ---------------------------------------------------------------------

    def marcar(self, id_dps: str, situacao: SituacaoEmissao, **dados) -> RegistroEmissao:
        """Muda a situação e grava os campos informados, confirmando na hora."""
        with transaction.atomic():
            linha = EmissaoDps.objects.select_for_update().filter(id_dps=id_dps).first()
            if linha is None:
                raise KeyError(id_dps)
            registro = _registro(linha)
            self._aplicar_marcacao(registro, situacao, dados)
            _copiar_para_linha(registro, linha)
            linha.save()
            return registro
