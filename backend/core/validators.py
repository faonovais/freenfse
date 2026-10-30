"""Validadores de documentos."""

import re

from django.core.exceptions import ValidationError

_PESOS_PRIMEIRO = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_SEGUNDO = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
# 12 posições numéricas ou alfanuméricas (CNPJ alfanumérico) + 2 dígitos verificadores.
_FORMATO = re.compile(r"[0-9A-Z]{12}[0-9]{2}")


def normalizar_cnpj(valor):
    """Remove pontuação e espaços e põe em maiúsculas."""
    return re.sub(r"[.\-/\s]", "", valor or "").upper()


def _digito(base, pesos):
    soma = sum((ord(caractere) - 48) * peso for caractere, peso in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def calcular_digitos_cnpj(base12):
    """Calcula os dois dígitos verificadores de uma base de 12 posições."""
    primeiro = _digito(base12, _PESOS_PRIMEIRO)
    segundo = _digito(base12 + str(primeiro), _PESOS_SEGUNDO)
    return f"{primeiro}{segundo}"


def cnpj_valido(valor):
    """Indica se o CNPJ (numérico ou alfanumérico) tem formato e dígitos válidos."""
    cnpj = normalizar_cnpj(valor)
    if not _FORMATO.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False
    return cnpj[12:] == calcular_digitos_cnpj(cnpj[:12])


def validar_cnpj(valor):
    """Validador de campo: recusa CNPJ com formato ou dígito verificador inválido."""
    if not cnpj_valido(valor):
        raise ValidationError("CNPJ inválido.", code="cnpj_invalido")


def formatar_cnpj(valor):
    """Formata como 00.000.000/0000-00."""
    cnpj = normalizar_cnpj(valor)
    if len(cnpj) != 14:
        return valor
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def normalizar_cpf(valor):
    """Remove pontuação e espaços, mantendo só os dígitos."""
    return re.sub(r"\D", "", valor or "")


def cpf_valido(valor):
    """Indica se o CPF tem 11 dígitos, não é sequência repetida e os dígitos verificadores batem."""
    cpf = normalizar_cpf(valor)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        pesos = range(tamanho + 1, 1, -1)
        soma = sum(int(digito) * peso for digito, peso in zip(cpf[:tamanho], pesos, strict=True))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def validar_cpf(valor):
    """Validador de campo: recusa CPF com formato ou dígito verificador inválido."""
    if not cpf_valido(valor):
        raise ValidationError("CPF inválido.", code="cpf_invalido")


def formatar_cpf(valor):
    """Formata como 000.000.000-00."""
    cpf = normalizar_cpf(valor)
    if len(cpf) != 11:
        return valor
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
