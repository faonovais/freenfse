"""Endereços do tomador e do destinatário exigidos pelo `cIndOp` (E0239, E0243, E0919; issue #33).

O Anexo VI da NT 009 manda a Sefin rejeitar a DPS quando o **município de incidência do IBS/CBS**
é o do endereço do tomador/adquirente ou do destinatário e essa pessoa não é identificada por CPF
ou CNPJ com endereço nacional. Qual endereço vale sai do Anexo VII (`local_fornecimento`, coluna
estruturada `NFSeLocIncidIBS`):

| Local do fornecimento | `indDest` | Regra | Quem precisa de CPF/CNPJ e endereço nacional |
|---|---|---|---|
| adquirente | 0 ou 1 | E0239 | o tomador |
| destinatário | 0 | E0243 | o tomador (que é o próprio destinatário) |
| destinatário | 1 | E0919 | o destinatário |

Também bloqueia o `cIndOp` que não consta do Anexo VII (E0901: indicador não suportado). Todas as
regras só valem quando o grupo de IBS/CBS vai na DPS (`ind_gIBSCBS = 1`) e o emitente é o
prestador (`tpEmit = 1`, o único caso deste sistema); sem o grupo nenhuma se aplica.

O módulo é **puro** (sem banco, sem rede): recebe os dados e devolve as pendências e os avisos. "CPF
ou CNPJ" é pessoa física ou jurídica **nacional** (estrangeiro não serve, mesmo com NIF); "endereço
nacional" é o endereço completo que o cadastro de pessoas já exige (logradouro, número, bairro, CEP
de 8 dígitos e município com código IBGE de 7 dígitos). Que o código IBGE exista é garantido pelo
cadastro de pessoas, que valida contra a tabela de municípios ao gravar. ADR 0011.
"""

import re
from dataclasses import dataclass, field

from core.validators import cnpj_valido, cpf_valido
from fiscal.referencias import local_fornecimento

E0239, E0243, E0901, E0919 = "E0239", "E0243", "E0901", "E0919"

CAMPO_DO_TOMADOR = "tomador"
CAMPO_DO_DESTINATARIO = "destinatario"
CAMPO_DO_INDICADOR = "ibs_cbs"

_ROTULOS = {"tomador": "o tomador", "destinatario": "o destinatário"}
_CAMPOS_DO_EXTERIOR = ("pais", "codigo_postal", "cidade", "estado")
_SUJEITO = {"tomador": "O tomador", "destinatario": "O destinatário"}
_ESCOLHA = {
    "tomador": "Escolha o tomador no cadastro de pessoas.",
    "destinatario": "Escolha o destinatário no cadastro de pessoas.",
}


@dataclass(frozen=True)
class Pendencia:
    """Algo que impede a nota: a regra da Sefin, o campo da tela e a mensagem didática."""

    regra: str
    campo: str
    mensagem: str


@dataclass
class Resultado:
    """O que a avaliação encontrou: `pendencias` bloqueiam; `avisos` só orientam."""

    pendencias: list = field(default_factory=list)
    avisos: list = field(default_factory=list)


def problemas_da_pessoa(pessoa):
    """Por que a pessoa não atende "CPF ou CNPJ e endereço nacional"; lista vazia se atende.

    `pessoa` é o snapshot do cadastro (`dict`) ou `None` (ninguém informado).
    """
    if not pessoa:
        return ["não foi informado"]
    tipo = pessoa.get("tipo")
    if tipo == "estrangeiro":
        return ["é estrangeiro (a regra exige pessoa física ou jurídica com CPF ou CNPJ)"]
    if tipo not in ("pf", "pj"):
        return ["não é pessoa física nem jurídica"]
    problemas = []
    documento = pessoa.get("documento") or ""
    if tipo == "pf" and not cpf_valido(documento):
        problemas.append("não tem CPF válido")
    elif tipo == "pj" and not cnpj_valido(documento):
        problemas.append("não tem CNPJ válido")
    if any((pessoa.get(campo) or "").strip() for campo in _CAMPOS_DO_EXTERIOR):
        problemas.append("tem endereço no exterior (a regra exige endereço no Brasil)")
        return problemas
    faltas = [
        rotulo
        for campo, rotulo in (("logradouro", "o logradouro"), ("numero", "o número"))
        if not (pessoa.get(campo) or "").strip()
    ]
    if not (pessoa.get("bairro") or "").strip():
        faltas.append("o bairro")
    if not re.fullmatch(r"\d{8}", pessoa.get("cep") or ""):
        faltas.append("o CEP (8 dígitos)")
    if not re.fullmatch(r"\d{7}", pessoa.get("codigo_municipio") or ""):
        faltas.append("o município (código IBGE de 7 dígitos)")
    if faltas:
        problemas.append("tem o endereço incompleto: falta " + ", ".join(faltas))
    return problemas


def _frase(problemas):
    return "; ".join(problemas)


def _pendencia_da_pessoa(regra, campo, pessoa, contexto, correcao):
    """Monta a pendência da regra para `pessoa`; `None` se ela atende."""
    problemas = problemas_da_pessoa(pessoa)
    if not problemas:
        return None
    nome = (pessoa or {}).get("nome") or ""
    quem = f"{_SUJEITO[campo]} “{nome}”" if nome else _SUJEITO[campo]
    if not pessoa:
        correcao = _ESCOLHA[campo]
    return Pendencia(
        regra=regra,
        campo=campo,
        mensagem=(
            f"Regra {regra} da Sefin: {contexto}, então {_ROTULOS[campo]} precisa ter CPF ou CNPJ "
            f"e endereço no Brasil completo. {quem} {_frase(problemas)}. {correcao}"
        ),
    )


def avaliar(*, exige_grupo, codigo_indicador, indicador_destinatario, tomador, destinatario):
    """Aplica E0901, E0239, E0243 e E0919 e devolve um `Resultado`.

    `exige_grupo`: o grupo de IBS/CBS vai na DPS (sem ele nada se aplica). `codigo_indicador`:
    o `cIndOp`. `indicador_destinatario`: `indDest` (0 = o destinatário é o próprio tomador;
    1 = outra pessoa). `tomador` e `destinatario`: os snapshots do cadastro (`dict`) ou `None`.
    """
    resultado = Resultado()
    if not exige_grupo:
        return resultado
    codigo = str(codigo_indicador or "").strip()
    local = local_fornecimento.local_do_fornecimento(codigo)
    if local is None:
        resultado.pendencias.append(
            Pendencia(
                regra=E0901,
                campo=CAMPO_DO_INDICADOR,
                mensagem=(
                    f"Regra {E0901} da Sefin: o indicador da operação {codigo or '(vazio)'} não "
                    "consta da tabela oficial de indicadores (Anexo VII) e não é aceito em NFS-e. "
                    "Corrija o indicador no cadastro do serviço, na nota ou no modelo."
                ),
            )
        )
        return resultado

    descricao = local_fornecimento.descricao(codigo)
    sobre = f"O indicador da operação {codigo} ({descricao})"
    if local == local_fornecimento.ADQUIRENTE:
        contexto = f"{sobre} tem o município de incidência no endereço do tomador/adquirente"
        pendencia = _pendencia_da_pessoa(
            E0239,
            CAMPO_DO_TOMADOR,
            tomador,
            contexto,
            "Escolha outro tomador, ajuste o cadastro dele em Pessoas ou troque o indicador "
            "da operação.",
        )
    elif local == local_fornecimento.DESTINATARIO and indicador_destinatario == 0:
        contexto = (
            f"{sobre} tem o município de incidência no endereço do destinatário, que aqui é o "
            "próprio tomador"
        )
        pendencia = _pendencia_da_pessoa(
            E0243,
            CAMPO_DO_TOMADOR,
            tomador,
            contexto,
            "Escolha outro tomador, ajuste o cadastro dele em Pessoas ou troque o indicador "
            "da operação.",
        )
    elif local == local_fornecimento.DESTINATARIO and indicador_destinatario == 1:
        contexto = f"{sobre} tem o município de incidência no endereço do destinatário"
        pendencia = _pendencia_da_pessoa(
            E0919,
            CAMPO_DO_DESTINATARIO,
            destinatario,
            contexto,
            "Escolha outro destinatário, ajuste o cadastro dele em Pessoas ou troque o "
            "indicador da operação.",
        )
    else:
        pendencia = None
    if pendencia is not None:
        resultado.pendencias.append(pendencia)
    elif (
        local == local_fornecimento.OUTRO
        and (aviso := local_fornecimento.aviso_do_texto(codigo))
        and problemas_da_pessoa(tomador)
    ):
        resultado.avisos.append(aviso)
    return resultado
