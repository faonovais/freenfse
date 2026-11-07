"""Extrai, dos anexos técnicos oficiais da NFS-e (NT 009), as tabelas usadas pelo sistema.

- **Anexo VI**, aba `MUN.INCID_INFO.SERV.`: onde incide o ISSQN de cada código de tributação
  nacional (estabelecimento do prestador, local da prestação ou estabelecimento do tomador).
- **Anexo VII**, aba `cIndOp Public`: o local do fornecimento de cada indicador da operação
  (`cIndOp`), usado pelas regras E0239, E0243 e E0919.
- **Anexo VIII**: item da LC 116 + NBS → indicador da operação (`cIndOp`) → `cClassTrib`.

Funções puras: recebem uma `Planilha` e devolvem dicionários prontos para gravar em JSON. Se a
planilha tiver uma forma inesperada, levantam `ErroDePlanilha`: é melhor recusar a carga do que
gravar uma regra fiscal adivinhada.
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from fiscal.referencias.xlsx import ErroDePlanilha

ABA_LOCALIDADE = "MUN.INCID_INFO.SERV."
ABA_CORRELACAO = "tabela geral"
ABA_REGRA_EXTERIOR = "REGRA OP NÃO ONE_EXT"
ABA_LOCAL_DO_FORNECIMENTO = "cIndOp Public"
INDOP = re.compile(r"\d{6}")

# Anexo VII — onde o município de incidência fica, para quem emite NFS-e. A classificação vem SÓ da
# coluna estruturada `NFSeLocIncidIBS` (decisão do Supervisor e do usuário, issue #33); qualquer
# valor novo nela recusa a carga, em vez de ser classificado por palpite.
ADQUIRENTE, DESTINATARIO, OUTRO = "adquirente", "destinatario", "outro"
LOCAL_NFSE = {
    "Endereço do Tomador/Adquirente": ADQUIRENTE,
    "Endereço do Destinatário": DESTINATARIO,
    "Estabelecimento do Prestador/Fornecedor": OUTRO,
    "Local da Prestação": OUTRO,
    "Local da Prestação (Início do Transporte)": OUTRO,
    "Local da Prestação (Local da Retirada)": OUTRO,
    "Localidade do Imóvel": OUTRO,
    "Local do Evento": OUTRO,
    "Localização do Trecho (NFS-e Via)": OUTRO,
    "-": OUTRO,
    "": OUTRO,
}
CABECALHO_DO_ANEXO_VII = {
    0: "Código indOp",
    3: "Local do fornecimento a ser identificado no DFe",
    7: "indNFSe",
    8: "indNFSe Via",
    9: "NFSeLocIncidIBS",
}


def sha256_do_arquivo(caminho):
    """SHA-256 (hex) do arquivo, como registrado no `LEIAME.md`."""
    resumo = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def gravar_json(dados, caminho):
    """Grava o JSON de forma estável (chaves ordenadas) e devolve o SHA-256 do arquivo."""
    texto = json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    Path(caminho).write_text(texto, encoding="utf-8")
    return sha256_do_arquivo(caminho)


def so_digitos(texto):
    """Mantém apenas os dígitos."""
    return "".join(c for c in str(texto) if c.isdigit())


def chaves_do_item(codigo_tributacao_nacional):
    """Chaves do Anexo VIII para um código de tributação nacional, da mais específica à geral.

    O anexo lista a maioria dos serviços pelo item da LC 116 (`AA.BB`), mas os códigos especiais
    do grupo 99 (ex.: `99.03.01`) pelo código completo (`AA.BB.CC`).
    """
    codigo = so_digitos(codigo_tributacao_nacional)
    if len(codigo) != 6:
        return []
    return [f"{codigo[:2]}.{codigo[2:4]}.{codigo[4:6]}", f"{codigo[:2]}.{codigo[2:4]}"]


# -- Anexo VI: localidade de incidência do ISSQN -------------------------------------------------


def extrair_localidade_incidencia(planilha):
    """`{cTribNac: regra}`, com a regra `EP`, `LP`, `ET` ou `SEM_INCIDENCIA`.

    As colunas da aba são: código, descrição, estabelecimento do prestador (EP), local da
    prestação (LP), estabelecimento do tomador (ET) e emitente na importação. Cada linha de dados
    precisa marcar **exatamente uma** entre EP, LP e ET, ou nenhuma (serviço sem incidência).
    """
    regras = {}
    for linha in planilha.linhas(ABA_LOCALIDADE):
        codigo = linha[0].strip() if linha else ""
        if not re.fullmatch(r"\d{5,6}", codigo):
            continue
        codigo = codigo.zfill(6)
        marcas = [(sigla, "X" in (linha[i] if len(linha) > i else "").upper())
                  for sigla, i in (("EP", 2), ("LP", 3), ("ET", 4))]  # fmt: skip
        marcadas = [sigla for sigla, marcada in marcas if marcada]
        if len(marcadas) > 1:
            raise ErroDePlanilha(f"O serviço {codigo} marca mais de uma localidade: {marcadas}.")
        if codigo in regras:
            raise ErroDePlanilha(f"O serviço {codigo} aparece duas vezes na aba de incidência.")
        regras[codigo] = marcadas[0] if marcadas else "SEM_INCIDENCIA"
    if len(regras) < 300:
        raise ErroDePlanilha(
            f"A aba de incidência trouxe só {len(regras)} serviços; o esperado são mais de 300."
        )
    return dict(sorted(regras.items()))


# -- Anexo VIII: item + NBS → INDOP → cClassTrib --------------------------------------------------


def extrair_correlacao_indop(planilha):
    """Associações do Anexo VIII, com as mesclagens expandidas.

    Devolve `{"itens": {item: {nbs: {indop: [cClassTrib…]}}}, "locais": {indop: texto},
    "exterior": {indop: indop_exterior}, "nao_onerosa": {indop: indop_nao_onerosa}}`.
    """
    grade = planilha.grade(ABA_CORRELACAO, expandir_mesclagens=True)
    ultima = max(linha for linha, _ in grade)
    itens = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    locais = {}
    for linha in range(2, ultima + 1):
        item, nbs, indop, local, classe = (
            grade.get((linha, coluna), "") for coluna in (0, 2, 6, 7, 8)
        )
        if not (item and nbs and indop and classe):
            continue
        if not INDOP.fullmatch(indop) or not re.fullmatch(r"\d{6}", classe):
            raise ErroDePlanilha(
                f"Linha {linha}: INDOP {indop!r} ou cClassTrib {classe!r} inválido."
            )
        if not re.fullmatch(r"\d{2}\.\d{2}(\.\d{2})?", item):
            raise ErroDePlanilha(
                f"Linha {linha}: item da LC 116 {item!r} fora do formato AA.BB ou AA.BB.CC."
            )
        itens[item][so_digitos(nbs)][indop].add(classe)
        if local:
            locais.setdefault(indop, local)
    if len(itens) < 150:
        raise ErroDePlanilha(f"O Anexo VIII trouxe só {len(itens)} itens da LC 116.")
    return {
        "itens": {
            item: {
                nbs: {indop: sorted(classes) for indop, classes in sorted(por_indop.items())}
                for nbs, por_indop in sorted(por_nbs.items())
            }
            for item, por_nbs in sorted(itens.items())
        },
        "locais": dict(sorted(locais.items())),
        **_extrair_regra_exterior(planilha),
    }


def _extrair_regra_exterior(planilha):
    """Aba `REGRA OP NÃO ONE_EXT`: o INDOP muda para adquirente no exterior e para não onerosa."""
    exterior, nao_onerosa = {}, {}
    for linha in planilha.linhas(ABA_REGRA_EXTERIOR):
        celulas = [c.strip() for c in linha] + [""] * 6
        base, no_exterior, base_nao_onerosa = celulas[1], celulas[2], celulas[4]
        if INDOP.fullmatch(base) and INDOP.fullmatch(no_exterior):
            exterior[base] = no_exterior
        if INDOP.fullmatch(base) and INDOP.fullmatch(base_nao_onerosa):
            nao_onerosa[base] = base_nao_onerosa
    if not exterior:
        raise ErroDePlanilha("A aba de regras de INDOP (exterior / não onerosa) veio sem códigos.")
    return {
        "exterior": dict(sorted(exterior.items())),
        "nao_onerosa": dict(sorted(nao_onerosa.items())),
    }


# -- Anexo VII: local do fornecimento de cada cIndOp --------------------------------------------


def _nomes_no_texto(texto):
    """Quem o texto livre do Anexo VII menciona: `adquirente` e/ou `destinatario` (lista)."""
    minusculo = texto.lower()
    nomes = []
    if "adquirente" in minusculo:
        nomes.append(ADQUIRENTE)
    if "destinat" in minusculo:
        nomes.append(DESTINATARIO)
    return nomes


def extrair_local_do_fornecimento(planilha):
    """`{cIndOp: {...}}` do Anexo VII, com o local do fornecimento classificado para a NFS-e.

    Cada indicador traz o texto oficial (`tipo`, `caracteristica`, `local_texto`), as marcas de
    documento (`nfse`: `S`, `` ou, para a NFS-e Via, `Via`), a coluna estruturada `local_nfse` e
    a `classe` (`adquirente`, `destinatario` ou `outro`) que sai **somente** dela. `texto_cita` é a
    lista de quem o texto livre menciona, para a conferência apontar o caso em que o texto cita o
    adquirente e a coluna estruturada não. Recusa a planilha se uma classificação não for
    mencionada pelo próprio texto do local do fornecimento.
    """
    grade = planilha.grade(ABA_LOCAL_DO_FORNECIMENTO)
    for coluna, esperado in CABECALHO_DO_ANEXO_VII.items():
        encontrado = " ".join(grade.get((1, coluna), "").split())
        if encontrado != esperado:
            raise ErroDePlanilha(
                f"Anexo VII: a coluna {coluna + 1} deveria se chamar {esperado!r}, "
                f"mas é {encontrado!r}."
            )
    indicadores = {}
    for linha in range(2, max(numero for numero, _ in grade) + 1):
        texto = [" ".join(grade.get((linha, coluna), "").split()) for coluna in range(10)]
        codigo = texto[0]
        if not codigo:
            continue
        if not INDOP.fullmatch(codigo):
            raise ErroDePlanilha(f"Anexo VII, linha {linha}: cIndOp {codigo!r} inválido.")
        if codigo in indicadores:
            raise ErroDePlanilha(f"Anexo VII: o indicador {codigo} aparece duas vezes.")
        local_nfse, marca_nfse, marca_via = texto[9], texto[7], texto[8]
        if local_nfse not in LOCAL_NFSE:
            raise ErroDePlanilha(
                f"Anexo VII: o indicador {codigo} traz o local de NFS-e {local_nfse!r}, que o "
                "sistema não conhece. Classifique-o conscientemente antes de importar."
            )
        if marca_nfse not in ("S", "") or marca_via not in ("S", ""):
            raise ErroDePlanilha(f"Anexo VII: marcas de documento inesperadas em {codigo}.")
        classe = LOCAL_NFSE[local_nfse]
        citado = _nomes_no_texto(texto[3])
        if classe in (ADQUIRENTE, DESTINATARIO) and classe not in citado:
            raise ErroDePlanilha(
                f"Anexo VII: o indicador {codigo} é de {classe} pela coluna de NFS-e, mas o texto "
                f"do local do fornecimento nomeia {citado or 'ninguém'}. Confira o anexo."
            )
        indicadores[codigo] = {
            "tipo": texto[1],
            "caracteristica": texto[2],
            "local_texto": texto[3],
            "local_nfse": local_nfse,
            "nfse": "Via" if marca_via == "S" else marca_nfse,
            "classe": classe,
            "texto_cita": citado,
        }
    if len(indicadores) < 30:
        raise ErroDePlanilha(
            f"O Anexo VII trouxe só {len(indicadores)} indicadores; esperados ~40."
        )
    return dict(sorted(indicadores.items()))
