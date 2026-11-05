"""Tabelas oficiais da NFS-e: leitor de `.xlsx`, extração, baixador e dados versionados."""

import datetime as dt
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from fiscal.referencias import anexos_rtc, calculadora, classificacao, incidencia, indop
from fiscal.referencias.xlsx import ErroDePlanilha, Planilha

DADOS = Path(__file__).resolve().parents[1] / "referencias" / "dados"


# -- planilhas sintéticas (nada oficial é necessário para testar a leitura) --------------------


def _coluna(indice):
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[indice]


def _gravar_xlsx(caminho, abas):
    """`abas`: `{nome: {"linhas": [[...]], "mesclagens": ["A2:A4"]}}` → `.xlsx` mínimo."""
    nomes = list(abas)
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, n in enumerate(nomes, 1)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(nomes) + 1)
            )
            + "</Relationships>",
        )
        for i, nome in enumerate(nomes, 1):
            linhas = abas[nome]["linhas"]
            corpo = ""
            for numero, linha in enumerate(linhas, 1):
                celulas = "".join(
                    f'<c r="{_coluna(c)}{numero}" t="inlineStr">'
                    f"<is><t>{escape(str(v))}</t></is></c>"
                    for c, v in enumerate(linha)
                    if v != ""
                )
                corpo += f'<row r="{numero}">{celulas}</row>'
            mesclas = abas[nome].get("mesclagens", [])
            mesclas_xml = (
                f'<mergeCells count="{len(mesclas)}">'
                + "".join(f'<mergeCell ref="{m}"/>' for m in mesclas)
                + "</mergeCells>"
                if mesclas
                else ""
            )
            z.writestr(
                f"xl/worksheets/sheet{i}.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{corpo}</sheetData>{mesclas_xml}</worksheet>",
            )
    return caminho


def test_o_leitor_expande_as_celulas_mescladas(tmp_path):
    arquivo = _gravar_xlsx(
        tmp_path / "a.xlsx",
        {"tabela": {"linhas": [["item", "nbs"], ["01.01", "n1"], ["", "n2"], ["", "n3"]],
                    "mesclagens": ["A2:A4"]}},
    )  # fmt: skip
    planilha = Planilha(arquivo)

    sem = planilha.grade("tabela")
    com = planilha.grade("tabela", expandir_mesclagens=True)

    assert (3, 0) not in sem and (4, 0) not in sem
    assert com[(2, 0)] == com[(3, 0)] == com[(4, 0)] == "01.01"
    assert planilha.linhas("tabela", expandir_mesclagens=True)[3] == ["01.01", "n3"]


def test_arquivo_que_nao_e_xlsx_e_aba_inexistente_sao_recusados(tmp_path):
    falso = tmp_path / "falso.xlsx"
    falso.write_bytes(b"isto nao e um zip")
    with pytest.raises(ErroDePlanilha, match="Não foi possível abrir"):
        Planilha(falso)

    arquivo = _gravar_xlsx(tmp_path / "ok.xlsx", {"a": {"linhas": [["x"]]}})
    with pytest.raises(ErroDePlanilha, match="não existe"):
        Planilha(arquivo).grade("b")


# -- Anexo VI: localidade de incidência --------------------------------------------------------


def _anexo_vi(tmp_path, linhas):
    cabecalho = [["LISTA NACIONAL"], ["CÓDIGO"], ["x"], ["", "", "EP", "LP", "ET"]]
    return Planilha(
        _gravar_xlsx(
            tmp_path / "vi.xlsx", {anexos_rtc.ABA_LOCALIDADE: {"linhas": cabecalho + linhas}}
        )
    )


def _servicos(quantidade=320):
    return [[str(10101 + n), f"serviço {n}", "X", "-", "-", "X"] for n in range(quantidade)]


def test_extrai_a_localidade_de_incidencia_de_cada_servico(tmp_path):
    linhas = _servicos()
    linhas[1] = ["30401", "locação", "-", "X", "-", "X"]
    linhas[2] = ["170501", "mão de obra", "-", "-", "X", "X"]
    linhas[3] = ["990101", "sem incidência", "-", "-", "-", "-"]
    linhas[4] = ["200101", "porto", "-", "(**) X", "-", "X"]

    regras = anexos_rtc.extrair_localidade_incidencia(_anexo_vi(tmp_path, linhas))

    assert regras["010101"] == "EP"  # o zero à esquerda que a planilha perdeu volta
    assert (regras["030401"], regras["170501"]) == ("LP", "ET")
    assert (regras["990101"], regras["200101"]) == ("SEM_INCIDENCIA", "LP")
    assert list(regras) == sorted(regras)


@pytest.mark.parametrize(
    ("alteracao", "mensagem"),
    [
        (lambda s: s.__setitem__(1, ["30401", "x", "X", "X", "-", "X"]), "mais de uma localidade"),
        (lambda s: s.append(["10101", "repetido", "X", "-", "-", "X"]), "duas vezes"),
        (lambda s: s.__delitem__(slice(10, None)), "só 10 serviços"),
    ],
    ids=["duas marcas", "código repetido", "tabela pequena"],
)
def test_planilha_de_incidencia_inesperada_e_recusada(tmp_path, alteracao, mensagem):
    linhas = _servicos()
    alteracao(linhas)

    with pytest.raises(ErroDePlanilha, match=mensagem):
        anexos_rtc.extrair_localidade_incidencia(_anexo_vi(tmp_path, linhas))


# -- Anexo VIII: item + NBS → INDOP → cClassTrib -----------------------------------------------


def _anexo_viii(tmp_path, *, itens=160, formato_ruim=False):
    linhas = [["Item", "Desc", "NBS", "NBS d", "SN", "SN d", "INDOP", "Local", "cClassTrib"]]
    mesclagens = []
    for n in range(itens):
        item = f"{1 + n // 90:02d}.{1 + n % 90:02d}"
        if formato_ruim and n == 0:
            item = "1.1"
        topo = len(linhas) + 1
        linhas.append(
            [item, "d", f"1.{1000 + n}.10.00", "", "9", "", "100301", "Domicílio", "000001"]
        )
        linhas.append(["", "", f"1.{1000 + n}.20.00", "", "", "", "", "", "200043"])
        mesclagens += [f"A{topo}:A{topo + 1}", f"G{topo}:G{topo + 1}", f"H{topo}:H{topo + 1}"]
    regra = [
        ["Aplicação IndOp"],
        [],
        ["", "P/S", "EXT", "", "P/S", "EXT"],
        ["", "NÃO", "SIM", "", "NÃO", "SIM"],
        ["SIM", "100101", "100102", "NÃO", "100201", ""],
        ["", "100301", "100302", "", "100401", ""],
    ]
    return Planilha(
        _gravar_xlsx(
            tmp_path / "viii.xlsx",
            {
                anexos_rtc.ABA_CORRELACAO: {"linhas": linhas, "mesclagens": mesclagens},
                anexos_rtc.ABA_REGRA_EXTERIOR: {"linhas": regra},
            },
        )
    )


def test_extrai_a_correlacao_do_anexo_viii_expandindo_as_mesclagens(tmp_path):
    dados = anexos_rtc.extrair_correlacao_indop(_anexo_viii(tmp_path))

    primeiro = dados["itens"]["01.01"]
    assert primeiro["110001000"] == {"100301": ["000001"]}  # NBS 1.1000.10.00
    assert primeiro["110002000"] == {"100301": ["200043"]}
    assert dados["locais"] == {"100301": "Domicílio"}
    assert dados["exterior"] == {"100101": "100102", "100301": "100302"}
    assert dados["nao_onerosa"] == {"100101": "100201", "100301": "100401"}


def test_anexo_viii_com_item_fora_do_formato_ou_pequeno_e_recusado(tmp_path):
    with pytest.raises(ErroDePlanilha, match="fora do formato"):
        anexos_rtc.extrair_correlacao_indop(_anexo_viii(tmp_path, formato_ruim=True))
    with pytest.raises(ErroDePlanilha, match="só 20 itens"):
        anexos_rtc.extrair_correlacao_indop(_anexo_viii(tmp_path, itens=20))


# -- baixador da classificação: fonte falsa, firewall e vigência -------------------------------


class FonteFalsa:
    """A calculadora em memória: `{codigo: (início, fim|None, aceita_nfse, exige_grupo)}`."""

    def __init__(self, classes, *, rejeicoes_iniciais=0, mudar_indicador_em=None):
        self.classes = classes
        self.rejeicoes_iniciais = rejeicoes_iniciais
        self.mudar_indicador_em = mudar_indicador_em
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if self.rejeicoes_iniciais:
            self.rejeicoes_iniciais -= 1
            return b"<html><head><title>Request Rejected</title></head></html>"
        caminho = url.removeprefix(calculadora.URL_BASE)
        if caminho == "versao":
            return json.dumps({"versaoApp": "teste", "versaoDb": "V1"}).encode()
        data = dt.date.fromisoformat(caminho.split("data=")[1])
        if m := re.match(r"classificacoes-tributarias/cbs-ibs/NFSE/(\d+)\?", caminho):
            _, _, aceita, exige = self.classes[m.group(1)]
            if self.mudar_indicador_em and data >= self.mudar_indicador_em:
                exige = not exige
            return json.dumps(
                {"validoParaSiglaDfeInformado": aceita, "exigeGrupoIbsCbs": exige}
            ).encode()
        lista = [
            {
                "codigo": codigo,
                "descricao": f"classe {codigo}",
                "tiposDfeClassificacao": [{"tipo": 91}] if aceita else [{"tipo": 55}],
            }
            for codigo, (inicio, fim, aceita, _) in self.classes.items()
            if inicio <= data and (fim is None or data <= fim)
        ]
        return json.dumps(lista).encode()


def _cliente(fonte):
    pausas = []
    cliente = calculadora.Calculadora(buscar=fonte, pausa=pausas.append)
    cliente.pausas = pausas
    return cliente


D = dt.date


def test_firewall_que_responde_html_com_200_gera_nova_tentativa_e_nunca_grava_lixo():
    fonte = FonteFalsa({"000001": (D(2026, 1, 1), None, True, True)}, rejeicoes_iniciais=2)
    cliente = _cliente(fonte)

    lista = cliente.classificacoes_em(D(2026, 5, 1))

    assert list(lista) == ["000001"] and len(fonte.urls) == 3
    assert any(p >= calculadora.ESPERA_DA_PRIMEIRA_NOVA_TENTATIVA for p in cliente.pausas)


def test_firewall_que_nao_cede_levanta_erro_depois_das_tentativas():
    fonte = FonteFalsa({"000001": (D(2026, 1, 1), None, True, True)}, rejeicoes_iniciais=99)

    with pytest.raises(calculadora.ErroDeFonte, match="4 tentativas"):
        _cliente(fonte).classificacoes_em(D(2026, 5, 1))
    assert len(fonte.urls) == calculadora.TENTATIVAS


def test_a_vigencia_e_descoberta_ao_dia_por_busca_binaria():
    fonte = FonteFalsa(
        {
            "000001": (D(2026, 1, 1), None, True, True),
            "100001": (D(2026, 1, 1), D(2026, 3, 14), True, False),
            "300001": (D(2027, 6, 10), None, True, True),
            "400001": (D(2026, 1, 1), None, False, True),
        }
    )

    tabela = {
        c["codigo"]: c
        for c in calculadora.montar_tabela(_cliente(fonte), D(2026, 1, 1), D(2027, 12, 31))
    }

    assert (
        tabela["000001"]["vigencia_inicio"] == "2026-01-01"
        and tabela["000001"]["vigencia_fim"] is None
    )
    assert tabela["100001"]["vigencia_fim"] == "2026-03-14"  # o último dia vigente, exato
    assert tabela["300001"]["vigencia_inicio"] == "2027-06-10"
    assert (tabela["000001"]["exige_grupo_ibs_cbs"], tabela["100001"]["exige_grupo_ibs_cbs"]) == (
        True,
        False,
    )
    assert (
        tabela["400001"]["aceita_nfse"] is False and tabela["400001"]["exige_grupo_ibs_cbs"] is None
    )


def test_classificacao_que_sai_e_volta_a_vigorar_e_recusada():
    class ComBuraco(FonteFalsa):
        def __call__(self, url):
            if "classificacoes-tributarias/cbs-ibs?" in url and "data=2026-02-01" in url:
                return json.dumps(
                    [{"codigo": "000009", "descricao": "x", "tiposDfeClassificacao": []}]
                ).encode()
            return super().__call__(url)

    fonte = ComBuraco(
        {"000001": (D(2026, 1, 1), None, True, True), "000002": (D(2026, 1, 1), None, True, True)}
    )

    with pytest.raises(calculadora.ErroDeFonte, match="sai e volta"):
        calculadora.montar_tabela(_cliente(fonte), D(2026, 1, 1), D(2026, 6, 30))


def test_indicador_de_nfse_que_muda_dentro_da_vigencia_e_recusado():
    fonte = FonteFalsa(
        {"000001": (D(2026, 1, 1), None, True, True)}, mudar_indicador_em=D(2026, 6, 1)
    )

    with pytest.raises(calculadora.ErroDeFonte, match="muda dentro da vigência"):
        calculadora.montar_tabela(_cliente(fonte), D(2026, 1, 1), D(2026, 12, 31))


# -- leitores sobre os arquivos versionados ----------------------------------------------------


def test_incidencia_dos_servicos_do_anexo_vi():
    regras = incidencia.todas_as_regras()
    contagem = {r: list(regras.values()).count(r) for r in set(regras.values())}

    assert contagem == {"EP": 277, "LP": 58, "ET": 1, "SEM_INCIDENCIA": 1}
    assert incidencia.regra_de_incidencia("010101") == "EP"
    assert incidencia.regra_de_incidencia("170501") == "ET"
    assert incidencia.regra_de_incidencia("200101") == "LP"  # art. 3º, §3º
    assert incidencia.regra_de_incidencia("999999") is None
    assert incidencia.origem()["arquivo"].startswith("anexovi-")


def test_sugestao_de_cindop_pelo_anexo_viii():
    unico = indop.sugerir("010101", "1.1502.10.00")  # NBS com ou sem pontuação
    assert unico == {
        "sugestao": "100301",
        "opcoes": ["100301"],
        "item": "01.01",
        "encontrado": True,
    }
    assert indop.sugerir("010101", "115021000")["sugestao"] == "100301"
    assert indop.classes_possiveis("010101", "115029000") == ["000001", "200043", "200044"]

    varias = indop.sugerir("010701", "115013000")
    assert varias["sugestao"] is None and varias["opcoes"] == ["050101", "050102", "100301"]

    ausente = indop.sugerir("010101", "999999999")
    assert ausente == {"sugestao": None, "opcoes": [], "item": "01.01", "encontrado": False}
    assert indop.sugerir("999999", "")["encontrado"] is False


def test_codigos_do_grupo_99_sao_procurados_pelo_codigo_completo():
    assert indop.correlacao("990301", "")[0] in (None, "99.03.01")
    assert any(
        chave.startswith("99.03.")
        for chave in json.loads((DADOS / "correlacao_indop.json").read_text())["itens"]
    )


def test_indop_para_adquirente_no_exterior_e_local_de_incidencia_do_ibs():
    assert indop.indop_para_exterior("100301") == "100302"
    assert indop.indop_para_exterior("123456") is None
    assert indop.local_de_incidencia_do_ibs("100301") == "Domicílio principal do adquirente"


@pytest.mark.parametrize(
    ("codigo", "indicador", "esperado"),
    [
        ("990301", "100301", ["E0902"]),
        ("990305", "020101", []),
        ("990301", "02ABCD", ["formato"]),
        ("010101", "100301", []),
        ("010101", "12345", ["formato"]),
        ("010101", "", ["formato"]),
    ],
)
def test_regra_e0902_do_grupo_99_03(codigo, indicador, esperado):
    assert [c for c, _ in indop.violacoes_do_indicador(codigo, indicador)] == esperado


def test_classificacao_com_vigencia_e_indicador_de_ibs_cbs():
    hoje = D(2026, 11, 5)
    exige = classificacao.consultar("000001", hoje)
    assert (exige.aceita_nfse, exige.exige_grupo_ibs_cbs) == (True, True)
    assert classificacao.consultar("410009", hoje).exige_grupo_ibs_cbs is False
    assert classificacao.consultar("000999", hoje) is None and not classificacao.existe("000999")

    assert classificacao.consultar("220001", D(2026, 1, 1)) is not None
    assert classificacao.consultar("220001", D(2026, 1, 2)) is None  # vigorou só em 01/01/2026
    assert classificacao.existe("220001")
    assert classificacao.consultar("220001", D(2026, 1, 1)).aceita_nfse is False
    assert classificacao.primeiro_dia_pesquisado() == D(2026, 1, 1)


def test_totais_da_tabela_de_classificacao():
    nfse = [c for c in classificacao.todas().values() if c.aceita_nfse]

    assert len(classificacao.todas()) == 173
    assert (len(nfse), sum(1 for c in nfse if c.exige_grupo_ibs_cbs)) == (73, 43)
    assert all(c.exige_grupo_ibs_cbs is not None for c in nfse)


def test_o_leiame_registra_o_sha256_de_cada_arquivo_versionado():
    leiame = (DADOS / "LEIAME.md").read_text(encoding="utf-8")
    for arquivo in (
        "localidade_incidencia.json",
        "correlacao_indop.json",
        "classificacao_tributaria.json",
    ):
        sha = hashlib.sha256((DADOS / arquivo).read_bytes()).hexdigest()
        assert f"`{arquivo}` | `{sha}`" in leiame, f"{arquivo}: o LEIAME está desatualizado"


def test_a_origem_dos_anexos_registra_o_sha256_do_arquivo_oficial():
    for leitor in (incidencia, indop):
        origem = leitor.origem()
        assert re.fullmatch(r"[0-9a-f]{64}", origem["sha256"])
        assert origem["url"].startswith("https://www.gov.br/nfse/") and origem["obtido_em"]
        assert origem["sha256"] in (DADOS / "LEIAME.md").read_text(encoding="utf-8")
