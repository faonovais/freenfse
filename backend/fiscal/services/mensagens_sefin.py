"""Tradução das respostas da Sefin para linguagem de quem emite a nota.

A Sefin responde com códigos (`E0014`) e textos técnicos. Aqui cada código conhecido ganha uma
explicação simples e o que fazer em seguida; o texto original da Sefin é sempre preservado
junto, para o suporte. Código desconhecido recebe uma orientação genérica, nunca é escondido.
"""

ORIENTACOES = {
    "E0006": (
        "O ambiente da nota (produção ou produção restrita) não confere com o da Sefin.",
        "Confira o ambiente em Parâmetros fiscais e tente de novo.",
    ),
    "E0008": (
        "A data e hora de emissão estão no futuro.",
        "Confira se o relógio do servidor está correto e tente de novo.",
    ),
    "E0014": (
        "Já existe uma nota com esta série e número.",
        "Não emita de novo: consulte a nota na Sefin para ver se ela já foi autorizada.",
    ),
    "E0016": (
        "A competência é anterior ao início do convênio do município.",
        "Use uma competência a partir da data de adesão do município à NFS-e Nacional.",
    ),
    "E0031": (
        "O ISS só pode ser retido pelo tomador quando o município de incidência é o dele.",
        "Revise se o ISS deve ser retido neste serviço.",
    ),
    "E0037": (
        "O município não tem convênio com a NFS-e Nacional neste ambiente.",
        "Confirme a adesão com a prefeitura e verifique o convênio em Parâmetros fiscais.",
    ),
    "E0128": (
        "Os dados de endereço do prestador devem vir do cadastro nacional.",
        "Não informe o endereço do prestador; atualize o cadastro da empresa na Receita.",
    ),
    "E0160": (
        "A situação da empresa no Simples Nacional não confere com a do cadastro nacional.",
        "Corrija o regime tributário em Parâmetros fiscais conforme o cadastro da Receita.",
    ),
    "E0188": (
        "Um CPF ou CNPJ informado é inválido.",
        "Revise o documento do tomador no cadastro de pessoas.",
    ),
    "E0315": (
        "O código de tributação municipal informado não é aceito.",
        "Revise o código de tributação municipal do serviço no cadastro de serviços.",
    ),
    "E0322": (
        "A NBS do serviço é obrigatória quando há informações de IBS/CBS.",
        "Informe a NBS no cadastro do serviço.",
    ),
    "E0710": (
        "O tipo de informação sobre o total de tributos não é permitido para o seu regime.",
        "Ajuste o percentual de tributos do Simples na nota ou deixe-o em branco.",
    ),
    "E0712": (
        "O tipo de informação sobre o total de tributos não é permitido para o seu regime.",
        "Ajuste o percentual de tributos do Simples na nota ou deixe-o em branco.",
    ),
    "E0718": (
        "O certificado digital não pertence ao emitente da nota.",
        "Envie o certificado A1 da própria empresa em Certificado A1.",
    ),
    "E0824": (
        "O prazo ou a regra do município não permite cancelar esta nota diretamente.",
        "Peça o cancelamento à prefeitura (análise fiscal). Se ela deferir, a nota aparece "
        "como cancelada aqui depois de uma consulta.",
    ),
    "E0840": (
        "Esta nota já está cancelada ou substituída na Sefin.",
        "Consulte a nota para atualizar a situação aqui.",
    ),
    "E1229": (
        "O arquivo foi enviado em codificação incorreta.",
        "Tente de novo; se persistir, avise o suporte.",
    ),
}

ORIENTACAO_GENERICA = (
    "A Sefin recusou a informação enviada.",
    "Corrija o dado indicado e envie de novo. Se não entender o motivo, guarde o código e "
    "procure o suporte.",
)


def explicar(codigo, descricao="", complemento=""):
    """Erro da Sefin em forma didática: código, explicação, o que fazer e o texto original."""
    explicacao, o_que_fazer = ORIENTACOES.get((codigo or "").upper(), ORIENTACAO_GENERICA)
    return {
        "codigo": codigo or "",
        "explicacao": explicacao,
        "orientacao": o_que_fazer,
        "descricao_original": descricao or "",
        "complemento": complemento or "",
    }


def resumo(erros):
    """Frase única para a lista de notas e para o topo do detalhe."""
    if not erros:
        return ""
    primeiro = erros[0]
    texto = f"{primeiro['explicacao']} {primeiro['orientacao']}"
    if len(erros) > 1:
        texto += f" (há mais {len(erros) - 1} problema(s) no detalhe da nota)"
    return texto
