"""Cálculo das datas de um agendamento (D12, D13, D17): função pura, sem banco e sem relógio.

Regras (todas no fuso `America/Sao_Paulo`; o instante gravado é sempre UTC):

- **Frequências:** única, diária, semanal (dias da semana), mensal (dia do mês), anual (dia e mês)
  e "a cada N" dias, semanas ou meses (`intervalo`). O intervalo conta a partir da data de início:
  a semana (segunda a domingo) e o mês da data de início são a "rodada zero".
- **Dia 29, 30 ou 31 em mês curto** vale o último dia do mês; **29/02 em ano não bissexto** vale
  28/02 (é a mesma regra: o dia é limitado ao tamanho do mês).
- **Feriado e fim de semana executam** normalmente (D17): não há calendário de feriados.
- **Fim da série:** data de fim (inclusive) **ou** número de execuções, nunca os dois.
- Nada é retroativo: a próxima execução é sempre a primeira ocorrência **depois** do instante dado.
"""

import calendar
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

UNICA = "unica"
DIARIA = "diaria"
SEMANAL = "semanal"
MENSAL = "mensal"
ANUAL = "anual"
FREQUENCIAS = (UNICA, DIARIA, SEMANAL, MENSAL, ANUAL)
# O "a cada N" existe para estas; única e anual têm intervalo fixo em 1.
COM_INTERVALO = (DIARIA, SEMANAL, MENSAL)

INTERVALO_MAXIMO = 365
ANO_MAXIMO = 9999


@dataclass(frozen=True)
class Regra:
    """Como um agendamento se repete.

    `dias_semana`: 0 = segunda … 6 = domingo. `dia_do_mes` serve ao mensal (1 a 31) e ao anual
    (junto de `mes`). `data_fim` e `max_execucoes` são mutuamente exclusivos.
    """

    frequencia: str
    hora: dt.time
    data_inicio: dt.date
    intervalo: int = 1
    dias_semana: tuple = ()
    dia_do_mes: int | None = None
    mes: int | None = None
    data_fim: dt.date | None = None
    max_execucoes: int | None = None


# --- Datas e instantes ---------------------------------------------------------------------


def ultimo_dia_do_mes(ano, mes):
    """Quantos dias tem o mês (28/29 em fevereiro conforme o ano)."""
    return calendar.monthrange(ano, mes)[1]


def instante(data, hora):
    """Instante (UTC) em que a `hora` de Brasília da `data` acontece."""
    return dt.datetime.combine(data, hora, tzinfo=FUSO).astimezone(dt.UTC)


def data_local(momento):
    """Devolva a data em Brasília do instante (o dia vale em Brasília, não em UTC)."""
    return momento.astimezone(FUSO).date()


# --- Validação -----------------------------------------------------------------------------


def validar(regra, *, hoje=None):
    """Erros da regra por campo (vazio = válida). Com `hoje`, recusa início no passado."""
    erros = {}
    frequencia = regra.frequencia
    if frequencia not in FREQUENCIAS:
        return {"frequencia": "Escolha uma frequência válida."}

    if frequencia in COM_INTERVALO:
        if not isinstance(regra.intervalo, int) or not 1 <= regra.intervalo <= INTERVALO_MAXIMO:
            erros["intervalo"] = f"Informe um intervalo entre 1 e {INTERVALO_MAXIMO}."
    elif regra.intervalo != 1:
        erros["intervalo"] = "Esta frequência não tem intervalo: repete a cada 1."

    if frequencia == SEMANAL:
        dias = list(regra.dias_semana)
        if not dias:
            erros["dias_semana"] = "Escolha pelo menos um dia da semana."
        elif any(not isinstance(d, int) or not 0 <= d <= 6 for d in dias):
            erros["dias_semana"] = "Os dias da semana vão de 0 (segunda) a 6 (domingo)."
    if frequencia == MENSAL:
        if regra.dia_do_mes is None or not 1 <= regra.dia_do_mes <= 31:
            erros["dia_do_mes"] = "Informe o dia do mês, de 1 a 31."
    if frequencia == ANUAL:
        if regra.mes is None or not 1 <= regra.mes <= 12:
            erros["mes"] = "Informe o mês, de 1 a 12."
        elif regra.dia_do_mes is None or not 1 <= regra.dia_do_mes <= ultimo_dia_do_mes(
            2024, regra.mes
        ):
            erros["dia_do_mes"] = "Esse dia não existe no mês escolhido."

    if regra.data_fim is not None and regra.max_execucoes is not None:
        erros["max_execucoes"] = (
            "Informe a data de fim OU o número de execuções, não os dois: o agendamento termina "
            "no que vier definido."
        )
    elif frequencia == UNICA and (regra.data_fim is not None or regra.max_execucoes is not None):
        erros["data_fim"] = "Um agendamento de execução única não tem fim nem limite de execuções."
    if regra.max_execucoes is not None and regra.max_execucoes < 1:
        erros["max_execucoes"] = "O número de execuções deve ser pelo menos 1."
    if regra.data_fim is not None and regra.data_fim < regra.data_inicio:
        erros["data_fim"] = "A data de fim não pode ser anterior à data de início."
    if hoje is not None and regra.data_inicio < hoje:
        erros["data_inicio"] = "A data de início não pode estar no passado."
    return erros


# --- Séries por frequência -----------------------------------------------------------------
# Cada gerador devolve as datas da série, em ordem, a partir de `a_partir` e da data de início,
# sem aplicar o fim nem o limite de execuções (quem consome aplica).


def _unica(regra, a_partir):
    if regra.data_inicio >= a_partir:
        yield regra.data_inicio


def _diaria(regra, a_partir):
    primeira = max(a_partir, regra.data_inicio)
    passos = -(-(primeira - regra.data_inicio).days // regra.intervalo)  # teto da divisão
    data = regra.data_inicio + dt.timedelta(days=passos * regra.intervalo)
    while data.year <= ANO_MAXIMO - 1:
        yield data
        data += dt.timedelta(days=regra.intervalo)


def _segunda(data):
    return data - dt.timedelta(days=data.weekday())


def _semanal(regra, a_partir):
    primeira = max(a_partir, regra.data_inicio)
    dias = sorted(set(regra.dias_semana))
    semana = _segunda(primeira)
    resto = ((semana - _segunda(regra.data_inicio)).days // 7) % regra.intervalo
    if resto:  # alinha à rodada do "a cada N semanas"
        semana += dt.timedelta(weeks=regra.intervalo - resto)
    while semana.year <= ANO_MAXIMO - 1:
        for dia in dias:
            data = semana + dt.timedelta(days=dia)
            if data >= primeira:
                yield data
        semana += dt.timedelta(weeks=regra.intervalo)


def _data_do_mes(ano, mes, dia):
    """O dia pedido, limitado ao último dia do mês (31 → 30/28/29)."""
    return dt.date(ano, mes, min(dia, ultimo_dia_do_mes(ano, mes)))


def _mensal(regra, a_partir):
    primeira = max(a_partir, regra.data_inicio)
    base = regra.data_inicio.year * 12 + regra.data_inicio.month - 1
    atual = primeira.year * 12 + primeira.month - 1
    resto = (atual - base) % regra.intervalo
    if resto:  # alinha à rodada do "a cada N meses"
        atual += regra.intervalo - resto
    while atual // 12 <= ANO_MAXIMO - 1:
        ano, mes = divmod(atual, 12)
        data = _data_do_mes(ano, mes + 1, regra.dia_do_mes)
        if data >= primeira:
            yield data
        atual += regra.intervalo


def _anual(regra, a_partir):
    primeira = max(a_partir, regra.data_inicio)
    ano = primeira.year
    while ano <= ANO_MAXIMO - 1:
        data = _data_do_mes(ano, regra.mes, regra.dia_do_mes)  # 29/02 → 28/02 em ano comum
        if data >= primeira:
            yield data
        ano += 1


_SERIES = {UNICA: _unica, DIARIA: _diaria, SEMANAL: _semanal, MENSAL: _mensal, ANUAL: _anual}


def datas_da_serie(regra, a_partir):
    """Datas da série a partir de `a_partir` (inclusive) até a data de fim, se houver."""
    for data in _SERIES[regra.frequencia](regra, a_partir):
        if regra.data_fim is not None and data > regra.data_fim:
            return
        yield data


# --- Próximas execuções --------------------------------------------------------------------


def proximas_execucoes(regra, *, executadas, depois_de, quantidade):
    """Os próximos `quantidade` instantes (UTC) **estritamente depois** de `depois_de`.

    `executadas` é quantas execuções já foram feitas com sucesso: com limite de execuções, só
    sobram `max_execucoes - executadas`. Execução que falhou ou foi perdida não conta, então a
    série segue até completar o limite.
    """
    if regra.max_execucoes is not None:
        quantidade = min(quantidade, regra.max_execucoes - executadas)
    instantes = []
    if quantidade <= 0:
        return instantes
    for data in datas_da_serie(regra, data_local(depois_de)):
        momento = instante(data, regra.hora)
        if momento <= depois_de:
            continue
        instantes.append(momento)
        if len(instantes) >= quantidade:
            break
    return instantes


def proxima_execucao(regra, *, executadas, depois_de):
    """O primeiro instante da série depois de `depois_de`, ou `None` se a série terminou."""
    encontrados = proximas_execucoes(
        regra, executadas=executadas, depois_de=depois_de, quantidade=1
    )
    return encontrados[0] if encontrados else None


def contar_ocorrencias_ate(regra, *, desde, ate, limite=1000):
    """Quantas ocorrências da série caem de `desde` (data, inclusive) até o instante `ate`.

    Serve ao aviso "N execuções foram puladas"; para de contar em `limite`.
    """
    total = 0
    for data in datas_da_serie(regra, desde):
        if instante(data, regra.hora) > ate or total >= limite:
            break
        total += 1
    return total
