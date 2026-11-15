"""Cadastro e catálogo oficial de serviços (LC 116 + NBS + IBS/CBS)."""

import re

from fiscal.referencias import classificacao, incidencia, indop, local_fornecimento


def _apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def consultar_catalogo_oficial(*, codigo_nacional="", nbs="", c_class_trib=""):
    """Consulta itens LC 116, NBS, cIndOp e classificações IBS/CBS nas referências oficiais."""
    cod = _apenas_digitos(codigo_nacional)
    nbs_limpa = _apenas_digitos(nbs)
    cclass_limpa = _apenas_digitos(c_class_trib)

    regras = incidencia.todas_as_regras()

    itens_lc116 = []
    for codigo, regra in sorted(regras.items()):
        digitos = _apenas_digitos(codigo)
        if cod and not digitos.startswith(cod):
            continue
        _chave, por_nbs = indop._por_nbs(digitos)
        if not por_nbs:
            continue
        regra_desc = incidencia.DESCRICAO.get(regra, "")
        itens_lc116.append(
            {
                "codigo": digitos,
                "codigo_formatado": (
                    f"{digitos[:2]}.{digitos[2:4]}.{digitos[4:6]}" if len(digitos) == 6 else codigo
                ),
                "regra_incidencia": regra,
                "descricao": regra_desc,
                "nbs_disponiveis": len(por_nbs),
            }
        )

    nbs_opcoes = []
    if len(cod) >= 4:
        _chave, por_nbs = indop._por_nbs(cod)
        for nbs_cod, indops in sorted(por_nbs.items()):
            nbs_opcoes.append({"nbs": nbs_cod, "indicadores": sorted(indops.keys())})

    indicadores = []
    classes_possiveis = set()
    if len(cod) == 6 and len(nbs_limpa) == 9:
        _item, correlacoes = indop.correlacao(cod, nbs_limpa)
        for indop_cod, classes in sorted((correlacoes or {}).items()):
            classes_possiveis.update(classes)
            indicadores.append(
                {
                    "codigo": indop_cod,
                    "local_fornecimento": local_fornecimento.descricao(indop_cod),
                    "classes_possiveis": list(classes),
                }
            )

    classificacoes = []
    for regra_class in classificacao.todas().values():
        if not regra_class.aceita_nfse:
            continue
        if cclass_limpa and not regra_class.codigo.startswith(cclass_limpa):
            continue
        classificacoes.append(
            {
                "codigo": regra_class.codigo,
                "cst": regra_class.codigo[:3],
                "descricao": regra_class.descricao,
                "exige_grupo_ibs_cbs": regra_class.exige_grupo_ibs_cbs,
                "sugerida_no_anexo_viii": (
                    regra_class.codigo in classes_possiveis if classes_possiveis else False
                ),
            }
        )
    classificacoes.sort(key=lambda item: (not item["sugerida_no_anexo_viii"], item["codigo"]))

    return {
        "itens_lc116": itens_lc116,
        "nbs_opcoes": nbs_opcoes,
        "indicadores": indicadores,
        "classificacoes": classificacoes,
    }


def salvar_servico_oficial(instancia, *, empresa=None):
    """Valida nas tabelas oficiais, grava `ServicoOficial` e vincula à empresa."""
    instancia.full_clean()
    instancia.save()
    if empresa is not None:
        empresa.servicos_oficiais.add(instancia)
    return instancia
