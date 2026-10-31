"""O que impede a empresa de emitir agora, em linguagem simples e com o caminho para resolver.

A interface mostra estes bloqueios antes de o usuário preencher a nota e o serviço de emissão os
confere de novo na hora de enviar: o estado da empresa pode mudar entre uma coisa e outra.
"""

from dataclasses import dataclass

from django.utils import timezone

from fiscal.models import Certificado, ParametrosFiscais


@dataclass(frozen=True)
class Bloqueio:
    """Um motivo para não emitir: `codigo` estável, `mensagem` didática e `tela` para corrigir."""

    codigo: str
    mensagem: str
    tela: str

    def para_dict(self):
        """Forma enviada à interface."""
        return {"codigo": self.codigo, "mensagem": self.mensagem, "tela": self.tela}


def verificar_prontidao(agora=None):
    """Lista os bloqueios da empresa ativa (vazia = pode emitir)."""
    agora = agora or timezone.now()
    parametros = ParametrosFiscais.obter()
    certificado = Certificado.objects.first()
    bloqueios = []

    if certificado is None:
        bloqueios.append(
            Bloqueio(
                "sem_certificado",
                "Falta o certificado digital A1 da empresa. Sem ele não é possível assinar nem "
                "enviar notas.",
                "/fiscal/certificado",
            )
        )
    elif certificado.vencido(agora):
        bloqueios.append(
            Bloqueio(
                "certificado_vencido",
                "O certificado digital da empresa venceu. Envie um certificado válido.",
                "/fiscal/certificado",
            )
        )

    if not parametros.codigo_municipio_emissor:
        bloqueios.append(
            Bloqueio(
                "sem_municipio",
                "Informe o município emissor da empresa nos parâmetros fiscais.",
                "/fiscal/parametros",
            )
        )
    elif not parametros.convenio_atual:
        bloqueios.append(
            Bloqueio(
                "convenio_nao_verificado",
                "Verifique se o município aderiu à NFS-e Nacional (neste ambiente) antes de "
                "emitir.",
                "/fiscal/parametros",
            )
        )
    elif (parametros.convenio_resultado or {}).get("aderente") is not True:
        bloqueios.append(
            Bloqueio(
                "convenio_nao_aderente",
                "O município não tem convênio confirmado com a NFS-e Nacional neste ambiente. "
                "As notas seriam rejeitadas. Confirme a adesão com a prefeitura e verifique "
                "novamente.",
                "/fiscal/parametros",
            )
        )

    precisa_apuracao = (
        parametros.regime_tributario == ParametrosFiscais.RegimeTributario.SIMPLES_NACIONAL
    )
    if precisa_apuracao and parametros.regime_apuracao_simples is None:
        bloqueios.append(
            Bloqueio(
                "regime_incompleto",
                "Informe como os tributos do Simples Nacional são apurados nos parâmetros fiscais.",
                "/fiscal/parametros",
            )
        )
    return bloqueios
