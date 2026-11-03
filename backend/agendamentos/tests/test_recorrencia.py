"""Cálculo de datas dos agendamentos: todas as frequências, limites de mês, fuso e fim da série.

Função pura, sem banco e com o relógio sempre injetado (`depois_de`).
"""

import datetime as dt

import pytest

from agendamentos import recorrencia as r

H = dt.time(8, 0)
INICIO = dt.date(2026, 1, 1)  # uma quinta-feira


def utc(texto):
    return dt.datetime.fromisoformat(texto).replace(tzinfo=dt.UTC)


def regra(**campos):
    padrao = {"frequencia": r.DIARIA, "hora": H, "data_inicio": INICIO}
    return r.Regra(**{**padrao, **campos})


ANTES_DO_INICIO = utc("2025-12-31T12:00")


def datas(regra_, quantidade, *, depois_de=ANTES_DO_INICIO, executadas=0):
    """As próximas datas (de Brasília) da série."""
    instantes = r.proximas_execucoes(
        regra_, executadas=executadas, depois_de=depois_de, quantidade=quantidade
    )
    return [r.data_local(i) for i in instantes]


def d(ano, mes, dia):
    return dt.date(ano, mes, dia)


# -- frequências --------------------------------------------------------------------------


def test_unica_tem_uma_data_e_depois_acaba():
    unica = regra(frequencia=r.UNICA, data_inicio=d(2026, 3, 10))

    assert datas(unica, 5) == [d(2026, 3, 10)]
    assert r.proxima_execucao(unica, executadas=1, depois_de=utc("2026-03-10T12:00")) is None


def test_diaria_executa_todo_dia():
    assert datas(regra(), 3) == [d(2026, 1, 1), d(2026, 1, 2), d(2026, 1, 3)]


def test_a_cada_n_dias_conta_a_partir_da_data_de_inicio():
    a_cada_3 = regra(intervalo=3)

    assert datas(a_cada_3, 4) == [d(2026, 1, 1), d(2026, 1, 4), d(2026, 1, 7), d(2026, 1, 10)]
    # retomando no meio da série, continua alinhado ao início (e não a partir de "hoje")
    assert datas(a_cada_3, 2, depois_de=utc("2026-01-05T12:00")) == [d(2026, 1, 7), d(2026, 1, 10)]


def test_semanal_nos_dias_escolhidos_sem_voltar_antes_do_inicio():
    # início numa quarta (07/01): a segunda anterior (05/01) não conta
    semanal = regra(frequencia=r.SEMANAL, data_inicio=d(2026, 1, 7), dias_semana=(0, 2, 4))

    assert datas(semanal, 5) == [
        d(2026, 1, 7), d(2026, 1, 9), d(2026, 1, 12), d(2026, 1, 14), d(2026, 1, 16),
    ]  # fmt: skip


def test_a_cada_n_semanas_pula_as_semanas_do_meio():
    quinzenal = regra(
        frequencia=r.SEMANAL, intervalo=2, data_inicio=d(2026, 1, 5), dias_semana=(0, 3)
    )

    assert datas(quinzenal, 6) == [
        d(2026, 1, 5), d(2026, 1, 8), d(2026, 1, 19), d(2026, 1, 22), d(2026, 2, 2), d(2026, 2, 5),
    ]  # fmt: skip


def test_a_cada_n_semanas_continua_alinhado_ao_inicio_ao_retomar_no_meio_da_serie():
    quinzenal = regra(
        frequencia=r.SEMANAL, intervalo=2, data_inicio=d(2026, 1, 5), dias_semana=(0, 3)
    )

    # terça da semana "de folga" (12 a 18/01): a próxima rodada é a semana de 19/01
    da_semana_de_folga = datas(quinzenal, 3, depois_de=utc("2026-01-13T12:00"))
    # quinta da semana 0, depois das 08:00: a próxima também é 19/01 (não a segunda semana)
    depois_da_quinta = datas(quinzenal, 2, depois_de=utc("2026-01-08T12:00"))

    assert da_semana_de_folga == [d(2026, 1, 19), d(2026, 1, 22), d(2026, 2, 2)]
    assert depois_da_quinta == [d(2026, 1, 19), d(2026, 1, 22)]


def test_semanal_atravessa_a_virada_do_ano():
    semanal = regra(frequencia=r.SEMANAL, data_inicio=d(2026, 12, 21), dias_semana=(0,))

    assert datas(semanal, 3, depois_de=utc("2026-12-20T12:00")) == [
        d(2026, 12, 21), d(2026, 12, 28), d(2027, 1, 4),
    ]  # fmt: skip


def test_mensal_no_dia_escolhido():
    mensal = regra(frequencia=r.MENSAL, dia_do_mes=15)

    assert datas(mensal, 3) == [d(2026, 1, 15), d(2026, 2, 15), d(2026, 3, 15)]


def test_mensal_com_inicio_depois_do_dia_comeca_no_mes_seguinte():
    mensal = regra(frequencia=r.MENSAL, dia_do_mes=15, data_inicio=d(2026, 1, 20))

    assert datas(mensal, 2) == [d(2026, 2, 15), d(2026, 3, 15)]


def test_mensal_atravessa_a_virada_do_ano():
    mensal = regra(frequencia=r.MENSAL, dia_do_mes=15, data_inicio=d(2026, 11, 1))

    assert datas(mensal, 4) == [d(2026, 11, 15), d(2026, 12, 15), d(2027, 1, 15), d(2027, 2, 15)]


def test_a_cada_n_meses():
    trimestral = regra(frequencia=r.MENSAL, intervalo=3, dia_do_mes=10, data_inicio=d(2026, 1, 10))

    assert datas(trimestral, 5) == [
        d(2026, 1, 10), d(2026, 4, 10), d(2026, 7, 10), d(2026, 10, 10), d(2027, 1, 10),
    ]  # fmt: skip


def test_a_cada_n_meses_continua_alinhado_ao_inicio_ao_retomar_no_meio_da_serie():
    trimestral = regra(frequencia=r.MENSAL, intervalo=3, dia_do_mes=10, data_inicio=d(2026, 1, 10))

    # em fevereiro (mês "de folga") e logo depois da execução de abril
    assert datas(trimestral, 2, depois_de=utc("2026-02-15T12:00")) == [
        d(2026, 4, 10),
        d(2026, 7, 10),
    ]
    assert datas(trimestral, 1, depois_de=utc("2026-04-10T12:00")) == [d(2026, 7, 10)]


def test_anual_no_dia_e_mes_escolhidos():
    anual = regra(frequencia=r.ANUAL, dia_do_mes=10, mes=3)

    assert datas(anual, 3) == [d(2026, 3, 10), d(2027, 3, 10), d(2028, 3, 10)]


# -- último dia do mês e 29/02 ---------------------------------------------------------------


def test_dia_31_vira_o_ultimo_dia_do_mes_em_mes_curto():
    mensal = regra(frequencia=r.MENSAL, dia_do_mes=31, data_inicio=d(2027, 1, 1))

    assert datas(mensal, 5, depois_de=utc("2026-12-31T12:00")) == [
        d(2027, 1, 31), d(2027, 2, 28), d(2027, 3, 31), d(2027, 4, 30), d(2027, 5, 31),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("dia", "ano", "esperado"),
    [
        (31, 2027, d(2027, 2, 28)),  # ano comum
        (31, 2028, d(2028, 2, 29)),  # ano bissexto
        (30, 2027, d(2027, 2, 28)),
        (30, 2028, d(2028, 2, 29)),
        (29, 2027, d(2027, 2, 28)),
        (29, 2028, d(2028, 2, 29)),
    ],
)
def test_fevereiro_recebe_o_ultimo_dia_do_ano(dia, ano, esperado):
    mensal = regra(frequencia=r.MENSAL, dia_do_mes=dia, data_inicio=d(ano, 2, 1))

    assert datas(mensal, 1, depois_de=utc(f"{ano}-01-31T12:00")) == [esperado]


def test_anual_29_de_fevereiro_vira_28_em_ano_nao_bissexto():
    anual = regra(frequencia=r.ANUAL, dia_do_mes=29, mes=2, data_inicio=d(2027, 1, 1))

    assert datas(anual, 4, depois_de=utc("2026-12-31T12:00")) == [
        d(2027, 2, 28), d(2028, 2, 29), d(2029, 2, 28), d(2030, 2, 28),
    ]  # fmt: skip


def test_anual_na_virada_do_ano():
    anual = regra(frequencia=r.ANUAL, dia_do_mes=31, mes=12)

    assert datas(anual, 2) == [d(2026, 12, 31), d(2027, 12, 31)]


# -- início no futuro, fim e limite --------------------------------------------------------


def test_inicio_no_futuro_nao_executa_antes():
    futuro = regra(data_inicio=d(2027, 3, 10))

    assert datas(futuro, 2, depois_de=utc("2026-11-01T12:00")) == [d(2027, 3, 10), d(2027, 3, 11)]


def test_data_de_fim_e_inclusiva():
    ate_dia_3 = regra(data_fim=d(2026, 1, 3))

    assert datas(ate_dia_3, 10) == [d(2026, 1, 1), d(2026, 1, 2), d(2026, 1, 3)]


def test_limite_de_execucoes_conta_so_as_realizadas():
    tres_vezes = regra(max_execucoes=3)

    assert len(datas(tres_vezes, 10, executadas=0)) == 3
    assert len(datas(tres_vezes, 10, executadas=2)) == 1
    assert datas(tres_vezes, 10, executadas=3) == []


def test_execucao_que_falhou_nao_conta_e_a_serie_segue():
    # 2 realizadas, 1 falhou no meio: ainda falta 1 para completar as 3
    tres_vezes = regra(max_execucoes=3)

    proximas = datas(tres_vezes, 10, depois_de=utc("2026-01-10T12:00"), executadas=2)

    assert proximas == [d(2026, 1, 11)]


def test_hora_de_hoje_ja_passou_a_proxima_e_amanha_mesmo_com_limite_de_uma_execucao():
    uma_vez = regra(max_execucoes=1)

    # 09:00 em Brasília, depois das 08:00: hoje já passou, não é retroativo
    assert datas(uma_vez, 5, depois_de=utc("2026-06-10T12:00")) == [d(2026, 6, 11)]


# -- feriado e fim de semana executam (D17) -----------------------------------------------


def test_feriado_e_fim_de_semana_executam_normalmente():
    natal = regra(data_inicio=d(2026, 12, 24))

    # 25/12 (Natal, sexta), 26/12 (sábado) e 27/12 (domingo)
    assert datas(natal, 4, depois_de=utc("2026-12-23T12:00")) == [
        d(2026, 12, 24), d(2026, 12, 25), d(2026, 12, 26), d(2026, 12, 27),
    ]  # fmt: skip
    primeiro_de_maio = regra(frequencia=r.MENSAL, dia_do_mes=1, data_inicio=d(2027, 5, 1))
    assert datas(primeiro_de_maio, 1, depois_de=utc("2027-04-30T12:00")) == [
        d(2027, 5, 1)
    ]  # sábado


# -- fuso America/Sao_Paulo ---------------------------------------------------------------


def test_o_instante_e_guardado_em_utc_mas_calculado_em_brasilia():
    assert r.instante(d(2026, 6, 10), dt.time(8, 0)) == utc("2026-06-10T11:00")
    assert r.instante(d(2026, 10, 31), dt.time(23, 30)) == utc("2026-11-01T02:30")


def test_a_data_local_na_virada_do_dia_em_utc_e_a_de_brasilia():
    # 02:30 UTC de 01/11 ainda é 31/10 em Brasília
    assert r.data_local(utc("2026-11-01T02:30")) == d(2026, 10, 31)


def test_proxima_execucao_na_virada_do_dia_usa_a_data_de_brasilia():
    # 22:00 de 31/10 em Brasília (já é 01/11 em UTC): o dia 31 ainda não acabou
    mensal_31 = regra(frequencia=r.MENSAL, dia_do_mes=31, hora=dt.time(23, 0))

    proxima = r.proxima_execucao(mensal_31, executadas=0, depois_de=utc("2026-11-01T01:00"))

    assert proxima == utc("2026-11-01T02:00")  # 23:00 de 31/10 em Brasília
    assert r.data_local(proxima) == d(2026, 10, 31)


def test_a_execucao_so_vence_na_hora_de_brasilia():
    diaria_2330 = regra(hora=dt.time(23, 30))

    antes = r.proxima_execucao(diaria_2330, executadas=0, depois_de=utc("2026-11-01T02:20"))
    depois = r.proxima_execucao(diaria_2330, executadas=0, depois_de=utc("2026-11-01T02:35"))

    assert antes == utc("2026-11-01T02:30")  # ainda hoje à noite (23:30 de 31/10)
    assert depois == utc("2026-11-02T02:30")  # a de hoje já passou: amanhã


# -- validação ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "campo"),
    [
        ({"frequencia": "quinzenal"}, "frequencia"),
        ({"intervalo": 0}, "intervalo"),
        ({"intervalo": 1000}, "intervalo"),
        ({"frequencia": r.ANUAL, "dia_do_mes": 10, "mes": 3, "intervalo": 2}, "intervalo"),
        ({"frequencia": r.SEMANAL, "dias_semana": ()}, "dias_semana"),
        ({"frequencia": r.SEMANAL, "dias_semana": (7,)}, "dias_semana"),
        ({"frequencia": r.MENSAL, "dia_do_mes": 32}, "dia_do_mes"),
        ({"frequencia": r.MENSAL}, "dia_do_mes"),
        ({"frequencia": r.ANUAL, "dia_do_mes": 30, "mes": 2}, "dia_do_mes"),
        ({"frequencia": r.ANUAL, "dia_do_mes": 10, "mes": 13}, "mes"),
        ({"data_fim": d(2026, 2, 1), "max_execucoes": 3}, "max_execucoes"),
        ({"frequencia": r.UNICA, "data_fim": d(2026, 2, 1)}, "data_fim"),
        ({"max_execucoes": 0}, "max_execucoes"),
        ({"data_fim": d(2025, 12, 31)}, "data_fim"),
    ],
)
def test_regras_invalidas_apontam_o_campo(campos, campo):
    assert campo in r.validar(regra(**campos))


@pytest.mark.parametrize(
    "campos",
    [
        {},
        {"frequencia": r.UNICA},
        {"frequencia": r.SEMANAL, "dias_semana": (0, 6), "intervalo": 2},
        {"frequencia": r.MENSAL, "dia_do_mes": 31, "intervalo": 12},
        {"frequencia": r.ANUAL, "dia_do_mes": 29, "mes": 2},  # 29/02 vale (28/02 em ano comum)
        {"data_fim": d(2026, 12, 31)},
        {"max_execucoes": 12},
    ],
)
def test_regras_validas_passam(campos):
    assert r.validar(regra(**campos)) == {}


def test_inicio_no_passado_so_e_recusado_quando_pedido():
    antigo = regra(data_inicio=d(2026, 1, 1))

    assert r.validar(antigo) == {}
    assert "data_inicio" in r.validar(antigo, hoje=d(2026, 6, 1))
    assert r.validar(antigo, hoje=d(2026, 1, 1)) == {}


# -- contrato do gerador: só datas a partir de `a_partir`, alinhadas ao início ---------------


@pytest.mark.parametrize(
    ("campos", "a_partir", "esperadas"),
    [
        ({"intervalo": 3}, d(2026, 1, 10), [d(2026, 1, 10), d(2026, 1, 13), d(2026, 1, 16)]),
        ({"intervalo": 3}, d(2026, 1, 11), [d(2026, 1, 13), d(2026, 1, 16), d(2026, 1, 19)]),
        (
            {
                "frequencia": r.SEMANAL,
                "intervalo": 2,
                "dias_semana": (0,),
                "data_inicio": d(2026, 1, 5),
            },
            d(2026, 1, 6),
            [d(2026, 1, 19), d(2026, 2, 2), d(2026, 2, 16)],
        ),
        (
            {
                "frequencia": r.MENSAL,
                "intervalo": 3,
                "dia_do_mes": 10,
                "data_inicio": d(2026, 1, 10),
            },
            d(2026, 1, 11),
            [d(2026, 4, 10), d(2026, 7, 10), d(2026, 10, 10)],
        ),
        (
            {"frequencia": r.ANUAL, "dia_do_mes": 10, "mes": 3},
            d(2027, 3, 11),
            [d(2028, 3, 10), d(2029, 3, 10), d(2030, 3, 10)],
        ),
    ],
)
def test_o_gerador_so_devolve_datas_a_partir_do_pedido_e_alinhadas_ao_inicio(
    campos, a_partir, esperadas
):
    serie = r.datas_da_serie(regra(**campos), a_partir)

    assert [next(serie) for _ in esperadas] == esperadas


# -- contagem de ocorrências puladas ----------------------------------------------------


def test_conta_as_ocorrencias_ate_um_instante_e_para_no_limite():
    diaria = regra()

    assert r.contar_ocorrencias_ate(diaria, desde=d(2026, 1, 1), ate=utc("2026-01-05T12:00")) == 5
    assert (
        r.contar_ocorrencias_ate(
            diaria, desde=d(2026, 1, 1), ate=utc("2026-12-31T12:00"), limite=10
        )
        == 10
    )
