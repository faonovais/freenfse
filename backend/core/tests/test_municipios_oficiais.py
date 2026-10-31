"""Conferência do arquivo de municípios com a tabela oficial do IBGE (leitor, comparação, comando).

A planilha oficial (DTB, `.ods`) é montada em código, no mesmo formato da do IBGE: nenhum teste
depende de rede nem do arquivo de 1,6 MB.
"""

import csv
import zipfile
from io import StringIO
from xml.sax.saxutils import escape

import pytest
from django.core.management import CommandError, call_command

from core.municipios import ErroNoArquivoDeMunicipios, ler_arquivo
from core.municipios_oficiais import comparar, gravar_csv, ler_tabela_oficial

CABECALHO = [
    "UF", "Nome_UF", "Região Geográfica Intermediária", "Nome Região Geográfica Intermediária",
    "Região Geográfica Imediata", "Nome Região Geográfica Imediata", "Município",
    "Código Município Completo", "Nome_Município",
]  # fmt: skip
NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
)


def linha_oficial(codigo, nome, nome_uf="Maranhão"):
    return [codigo[:2], nome_uf, "2101", "São Luís", "210001", "São Luís", codigo[2:], codigo, nome]


def conteudo(linhas, data_base="31/12/2025", doctype=""):
    def celula(texto):
        return (
            '<table:table-cell office:value-type="string">'
            f"<text:p>{escape(texto)}</text:p></table:table-cell>"
        )

    corpo = "".join(
        "<table:table-row>"
        + "".join(celula(c) for c in linha)
        + '<table:table-cell table:number-columns-repeated="1000"/></table:table-row>'
        for linha in [
            ["TÍTULO : BET - BANCO DE ESTRUTURAS TERRITORIAIS"],
            ["RELATÓRIO DE DIVISÃO TERRITORIAL BRASILEIRA"],
            ["UF: 99 - BRASIL"],
            [f"DATA BASE: {data_base}"],
            CABECALHO,
            *linhas,
        ]
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>{doctype}<office:document-content {NS}>'
        f'<office:body><office:spreadsheet><table:table table:name="DTB_Municípios">{corpo}'
        "</table:table></office:spreadsheet></office:body></office:document-content>"
    )


def ods(caminho, linhas, **opcoes):
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        pacote.writestr("content.xml", conteudo(linhas, **opcoes))
    return caminho


def dtb_zip(caminho, linhas, nome="RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods", **opcoes):
    interno = ods(caminho.parent / "interno.ods", linhas, **opcoes)
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.write(interno, nome)
        pacote.writestr("RELATORIO_DTB_BRASIL_2025_DISTRITOS.ods", b"outro arquivo")
    return caminho


LINHAS = [
    linha_oficial("2101400", "Balsas"),
    linha_oficial("2111300", "São Luís"),
    linha_oficial("4209607", "Lauro Müller", "Santa Catarina"),
]

MUNICIPIOS_ESPERADOS = [
    ("2101400", "Balsas", "MA"),
    ("2111300", "São Luís", "MA"),
    ("4209607", "Lauro Müller", "SC"),
]


# -- leitor ---------------------------------------------------------------------------------


def test_le_a_planilha_dentro_do_zip_com_data_base_e_hashes(tmp_path):
    tabela = ler_tabela_oficial(dtb_zip(tmp_path / "DTB_2025.zip", LINHAS))

    assert tabela.municipios == MUNICIPIOS_ESPERADOS
    assert tabela.data_base == "31/12/2025" and tabela.nome_do_arquivo == "DTB_2025.zip"
    assert len(tabela.sha256_do_arquivo) == len(tabela.sha256_da_planilha) == 64
    assert tabela.sha256_do_arquivo != tabela.sha256_da_planilha


def test_le_a_planilha_solta_e_ignora_as_colunas_vazias_repetidas(tmp_path):
    tabela = ler_tabela_oficial(ods(tmp_path / "municipios.ods", LINHAS))

    assert [m[0] for m in tabela.municipios] == ["2101400", "2111300", "4209607"]


@pytest.mark.parametrize(
    ("linhas", "trecho"),
    [
        ([linha_oficial("210140", "Curto")], "Curto"),  # código com 6 dígitos
        ([["11", "Rondônia", "", "", "", "", "00015", "2100015", "UF não bate"]], "não bate"),
        ([linha_oficial("2101400", "Balsas"), linha_oficial("2101400", "Balsas")], "repetido"),
        ([linha_oficial("2101400", "")], "2101400"),  # nome vazio
    ],
)
def test_planilha_inconsistente_e_recusada_com_a_linha(tmp_path, linhas, trecho):
    with pytest.raises(ErroNoArquivoDeMunicipios, match=r"Linha \d+ da planilha") as erro:
        ler_tabela_oficial(ods(tmp_path / "ruim.ods", linhas))

    assert trecho in str(erro.value)


def test_arquivo_que_nao_e_a_planilha_de_municipios_e_recusado(tmp_path):
    sem_planilha = tmp_path / "vazio.zip"
    with zipfile.ZipFile(sem_planilha, "w") as pacote:
        pacote.writestr("RELATORIO_DTB_BRASIL_2025_DISTRITOS.ods", b"x")
    nao_ods = tmp_path / "texto.ods"
    nao_ods.write_text("isto não é uma planilha")
    sem_cabecalho = tmp_path / "sem_cabecalho.ods"
    with zipfile.ZipFile(sem_cabecalho, "w") as pacote:
        pacote.writestr("content.xml", f"<office:document-content {NS}/>")

    with pytest.raises(ErroNoArquivoDeMunicipios, match="achei 0"):
        ler_tabela_oficial(sem_planilha)
    with pytest.raises(ErroNoArquivoDeMunicipios, match="não é uma planilha"):
        ler_tabela_oficial(nao_ods)
    with pytest.raises(ErroNoArquivoDeMunicipios, match="cabeçalho"):
        ler_tabela_oficial(sem_cabecalho)


def test_entidade_externa_do_xml_nao_e_resolvida(tmp_path):
    segredo = tmp_path / "segredo.txt"
    segredo.write_text("CONTEUDO-SECRETO")
    doctype = f'<!DOCTYPE x [<!ENTITY ext SYSTEM "file://{segredo}">]>'
    xml = conteudo([linha_oficial("2101400", "NOME")], doctype=doctype)
    caminho = tmp_path / "xxe.ods"
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("content.xml", xml.replace("NOME", "Bal&ext;sas"))

    try:
        tabela = ler_tabela_oficial(caminho)
    except ErroNoArquivoDeMunicipios:
        return  # recusar o arquivo também é aceitável: o que não pode é ler o segredo
    assert "CONTEUDO-SECRETO" not in "".join(nome for _, nome, _ in tabela.municipios)


# -- comparação -----------------------------------------------------------------------------


def test_comparar_conta_iguais_diferentes_faltantes_e_a_mais():
    versionado = [
        ("1", "Igual", "MA"),
        ("2", "Nome velho", "MA"),
        ("3", "Mesma", "PI"),
        ("5", "Só aqui", "BA"),
    ]
    oficial = [
        ("1", "Igual", "MA"),
        ("2", "Nome novo", "MA"),
        ("3", "Mesma", "MA"),
        ("4", "Só lá", "SP"),
    ]

    relatorio = comparar(versionado, oficial)

    assert relatorio.iguais == 1 and not relatorio.conferido
    assert relatorio.diferentes == [
        ("2", ("Nome velho", "MA"), ("Nome novo", "MA")),
        ("3", ("Mesma", "PI"), ("Mesma", "MA")),  # a UF diferente também conta
    ]
    assert relatorio.faltantes == [("4", "Só lá", "SP")]
    assert relatorio.a_mais == [("5", "Só aqui", "BA")]


def test_arquivos_identicos_conferem():
    linhas = [("1", "A", "MA"), ("2", "B", "PI")]

    relatorio = comparar(linhas, list(reversed(linhas)))

    assert relatorio.conferido and relatorio.iguais == 2


# -- comando --------------------------------------------------------------------------------


def versionado(tmp_path, linhas):
    caminho = tmp_path / "versionado.csv"
    with caminho.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(["codigo_ibge", "nome", "uf"])
        escritor.writerows(linhas)
    return caminho


def test_gravar_csv_escreve_o_formato_do_arquivo_versionado(tmp_path):
    destino = tmp_path / "saida.csv"

    sha = gravar_csv([("2111300", "São Luís", "MA"), ("2101400", "Balsas", "MA")], destino)

    assert destino.read_text(encoding="utf-8") == (
        "codigo_ibge,nome,uf\n2101400,Balsas,MA\n2111300,São Luís,MA\n"
    )
    assert ler_arquivo(destino) == [("2101400", "Balsas", "MA"), ("2111300", "São Luís", "MA")]
    assert len(sha) == 64


def test_comando_relata_as_diferencas_e_so_grava_com_gravar(tmp_path, monkeypatch):
    oficial = dtb_zip(tmp_path / "DTB_2025.zip", LINHAS)
    atual = versionado(
        tmp_path,
        [("2101400", "Balsas", "MA"), ("2111300", "Sao Luis", "MA"), ("2199999", "X", "MA")],
    )
    monkeypatch.setattr("core.management.commands.comparar_municipios_ibge.ARQUIVO_PADRAO", atual)
    monkeypatch.setattr("core.municipios.ARQUIVO_PADRAO", atual)
    saida = StringIO()

    call_command("comparar_municipios_ibge", str(oficial), stdout=saida)

    texto = saida.getvalue()
    assert "data-base 31/12/2025" in texto and "Iguais: 1" in texto
    assert "Diferentes (nome ou UF): 1" in texto and "Faltantes no arquivo versionado: 1" in texto
    assert "A mais no arquivo versionado: 1" in texto
    assert "DIFERENTE 2111300: Sao Luis/MA -> São Luís/MA" in texto
    assert "FALTA 4209607: Lauro Müller/SC" in texto and "A MAIS 2199999" in texto
    assert atual.read_text(encoding="utf-8").count("Sao Luis") == 1  # sem --gravar, nada mudou


def test_comando_com_gravar_corrige_inclui_e_remove_o_que_nao_e_oficial(tmp_path, monkeypatch):
    oficial = dtb_zip(tmp_path / "DTB_2025.zip", LINHAS)
    atual = versionado(tmp_path, [("2111300", "Sao Luis", "MA"), ("2199999", "X", "MA")])
    monkeypatch.setattr("core.management.commands.comparar_municipios_ibge.ARQUIVO_PADRAO", atual)
    monkeypatch.setattr("core.municipios.ARQUIVO_PADRAO", atual)
    saida = StringIO()

    call_command("comparar_municipios_ibge", str(oficial), "--gravar", stdout=saida)

    assert ler_arquivo(atual) == MUNICIPIOS_ESPERADOS
    assert "CSV gravado" in saida.getvalue()
    saida = StringIO()
    call_command("comparar_municipios_ibge", str(oficial), stdout=saida)
    assert "confere com a tabela oficial" in saida.getvalue()


def test_comando_recusa_arquivo_inexistente_ou_invalido(tmp_path):
    with pytest.raises(CommandError):
        call_command("comparar_municipios_ibge", str(tmp_path / "nao_existe.zip"))
    ruim = tmp_path / "ruim.zip"
    ruim.write_bytes(b"nao e zip")
    with pytest.raises((CommandError, zipfile.BadZipFile)):
        call_command("comparar_municipios_ibge", str(ruim))


# -- o arquivo versionado depois da conferência -----------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "nome", "uf"),
    [
        ("4209607", "Lauro Müller", "SC"),
        ("5107800", "Santo Antônio de Leverger", "MT"),
        ("2400208", "Assú", "RN"),
        ("1400605", "São Luiz do Anauá", "RR"),
        ("3200706", "Atílio Vivácqua", "ES"),
    ],
)
def test_arquivo_versionado_traz_a_grafia_oficial_das_correcoes(codigo, nome, uf):
    assert (codigo, nome, uf) in set(ler_arquivo())
