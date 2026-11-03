"""Cálculo dos valores da nota (ISS, retenções e líquido), sempre em `Decimal`.

A fonte dos percentuais é o **snapshot do serviço** guardado na nota, nunca o cadastro atual.
O arredondamento é "meio para cima" em centavos, o usual nas prefeituras; se uma prefeitura
usar outra regra, a Sefin devolve a divergência na rejeição e a regra muda aqui, num lugar só.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVOS = Decimal("0.01")
CEM = Decimal("100")


class ErroDeValores(Exception):
    """Valores da nota inconsistentes; `erros` mapeia o campo à mensagem para o usuário."""

    def __init__(self, erros):
        """Guarda os erros por campo e os junta na mensagem."""
        super().__init__("; ".join(erros.values()))
        self.erros = erros


def arredondar(valor):
    """Centavos, meio para cima."""
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def decimal_ou_none(valor, campo, erros, *, obrigatorio=False):
    """Converta texto ou número em `Decimal` não negativo, registrando o erro do campo."""
    if valor is None or valor == "":
        if obrigatorio:
            erros[campo] = "Informe o valor."
        return None
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        erros[campo] = "Valor inválido. Use números, por exemplo 1500.00."
        return None
    if not numero.is_finite() or numero < 0:
        erros[campo] = "O valor não pode ser negativo."
        return None
    if numero != arredondar(numero):
        erros[campo] = "Use no máximo 2 casas decimais."
        return None
    return numero


@dataclass(frozen=True)
class Totais:
    """Resultado do cálculo, pronto para mostrar e para guardar na nota."""

    valor_servico: Decimal
    desconto_incondicionado: Decimal
    desconto_condicionado: Decimal
    deducao: Decimal
    base_calculo: Decimal
    aliquota_iss: Decimal | None
    valor_iss: Decimal
    iss_retido: bool
    retencao_irrf: Decimal
    retencao_csll: Decimal
    retencao_inss: Decimal
    total_retencoes: Decimal
    valor_liquido: Decimal

    def para_dict(self):
        """Forma gravada no JSON da nota (valores em texto, sem perda)."""
        return {
            campo: (str(valor) if isinstance(valor, Decimal) else valor)
            for campo, valor in self.__dict__.items()
        }


def _percentual(servico, campo):
    valor = servico.get(campo)
    return Decimal(str(valor)) if valor not in (None, "") else Decimal("0")


def calcular(valores, servico):
    """Calcula os totais a partir dos `valores` informados e do snapshot do `servico`.

    Levanta `ErroDeValores` com uma mensagem por campo.
    """
    erros = {}
    bruto = decimal_ou_none(valores.get("servico"), "servico", erros, obrigatorio=True)
    incondicionado = decimal_ou_none(
        valores.get("desconto_incondicionado"), "desconto_incondicionado", erros
    ) or Decimal("0")
    condicionado = decimal_ou_none(
        valores.get("desconto_condicionado"), "desconto_condicionado", erros
    ) or Decimal("0")
    deducao_valor = decimal_ou_none(valores.get("deducao_valor"), "deducao_valor", erros)
    deducao_pct = decimal_ou_none(valores.get("deducao_percentual"), "deducao_percentual", erros)
    if deducao_valor is not None and deducao_pct is not None:
        erros["deducao_valor"] = "Informe a dedução em valor ou em percentual, não nos dois."
    if bruto is not None and bruto <= 0:
        erros["servico"] = "O valor do serviço deve ser maior que zero."
    if erros:
        raise ErroDeValores(erros)

    if incondicionado > bruto:
        erros["desconto_incondicionado"] = "O desconto não pode ser maior que o valor do serviço."
    if condicionado > bruto:
        erros["desconto_condicionado"] = "O desconto não pode ser maior que o valor do serviço."
    apos_desconto = bruto - incondicionado
    if deducao_pct is not None:
        if deducao_pct > CEM:
            erros["deducao_percentual"] = "O percentual de dedução não pode passar de 100%."
        deducao = arredondar(apos_desconto * deducao_pct / CEM)
    else:
        deducao = deducao_valor or Decimal("0")
    if deducao > apos_desconto:
        erros["deducao_valor"] = "A dedução não pode ser maior que o valor depois do desconto."
    if erros:
        raise ErroDeValores(erros)

    base = apos_desconto - deducao
    aliquota = servico.get("aliquota_iss")
    aliquota = Decimal(str(aliquota)) if aliquota not in (None, "") else None
    valor_iss = arredondar(base * aliquota / CEM) if aliquota is not None else Decimal("0")
    iss_retido = bool(servico.get("iss_retido")) and valor_iss > 0

    irrf = arredondar(base * _percentual(servico, "retencao_irrf") / CEM)
    csll = arredondar(base * _percentual(servico, "retencao_csll") / CEM)
    inss = arredondar(base * _percentual(servico, "retencao_inss") / CEM)
    retencoes = irrf + csll + inss + (valor_iss if iss_retido else Decimal("0"))
    liquido = bruto - incondicionado - retencoes
    return Totais(
        valor_servico=bruto,
        desconto_incondicionado=incondicionado,
        desconto_condicionado=condicionado,
        deducao=deducao,
        base_calculo=base,
        aliquota_iss=aliquota,
        valor_iss=valor_iss,
        iss_retido=iss_retido,
        retencao_irrf=irrf,
        retencao_csll=csll,
        retencao_inss=inss,
        total_retencoes=retencoes,
        valor_liquido=liquido,
    )
