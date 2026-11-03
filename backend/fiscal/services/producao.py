"""O que falta para a empresa trocar para o ambiente de produção (notas com valor fiscal).

A troca exige, além da permissão `config.editar` e da confirmação digitada na tela:

1. **Certificado A1 válido**: enviado, dentro da validade e com o CNPJ conferido (o da empresa,
   ou o de outro estabelecimento da mesma raiz quando isso foi autorizado no envio);
2. **Município emissor** informado;
3. **Convênio do município com a NFS-e Nacional vigente em produção**, consultado **na hora da
   troca**: o município aderiu (`aderente` verdadeiro) e a data de ativação já chegou. Uma
   verificação antiga na produção restrita não vale: o convênio é por ambiente.

Aqui ficam só as regras (funções puras, sem rede nem banco). Quem consulta e grava é
`fiscal.services.parametros`.
"""

import datetime as dt

from django.utils import timezone

from fiscal.services.bloqueios import Bloqueio
from fiscal.services.certificado import divergencia_de_cnpj

TELA_CERTIFICADO = "/fiscal/certificado"
TELA_PARAMETROS = "/fiscal/parametros"


def mensagem_das_pendencias(pendencias):
    """Texto único e didático que lista tudo o que falta, numerado."""
    itens = " ".join(f"({i}) {p.mensagem}" for i, p in enumerate(pendencias, start=1))
    return f"Ainda não é possível trocar para o ambiente de produção. Resolva antes: {itens}"


class ProducaoNaoLiberada(Exception):
    """A empresa ainda não cumpre o que a produção exige; `pendencias` diz o que falta."""

    def __init__(self, pendencias):
        """Guarda as pendências e monta a mensagem didática com todas elas."""
        self.pendencias = list(pendencias)
        super().__init__(mensagem_das_pendencias(self.pendencias))


def pendencias_locais(*, empresa, parametros, certificado, agora=None):
    """O que falta e dá para saber sem rede: certificado (existe, vale, CNPJ) e município."""
    agora = agora or timezone.now()
    pendencias = []

    if certificado is None:
        pendencias.append(
            Bloqueio(
                "sem_certificado",
                "Envie o certificado digital A1 da empresa: sem ele não é possível assinar nem "
                "enviar notas, nem consultar o convênio do município.",
                TELA_CERTIFICADO,
            )
        )
    else:
        divergencia = divergencia_de_cnpj(
            certificado.cnpj_titular, empresa.cnpj, mesma_raiz=certificado.mesma_raiz_autorizada
        )
        if divergencia:
            pendencias.append(Bloqueio("certificado_cnpj", divergencia, TELA_CERTIFICADO))
        if certificado.valido_de > agora:
            pendencias.append(
                Bloqueio(
                    "certificado_ainda_nao_vale",
                    f"O certificado só passa a valer em {_data(certificado.valido_de)}. "
                    "Envie um certificado que já esteja em vigor.",
                    TELA_CERTIFICADO,
                )
            )
        elif certificado.vencido(agora):
            pendencias.append(
                Bloqueio(
                    "certificado_vencido",
                    f"O certificado digital da empresa venceu em {_data(certificado.valido_ate)}. "
                    "Envie um certificado válido.",
                    TELA_CERTIFICADO,
                )
            )

    if not parametros.codigo_municipio_emissor:
        pendencias.append(
            Bloqueio(
                "sem_municipio",
                "Informe o município emissor da empresa nos parâmetros fiscais.",
                TELA_PARAMETROS,
            )
        )
    return pendencias


def avaliar_convenio(resultado, *, lugar, hoje=None):
    """Devolva a pendência do convênio **em produção**, ou `None` se ele estiver vigente.

    Vigente = o município aderiu **e** a data de ativação (quando informada) já chegou. Resposta
    que não deixa claro, ou data ilegível, não libera: na dúvida, a troca não é feita.
    """
    hoje = hoje or timezone.localdate()
    if resultado.aderente is False:
        return Bloqueio(
            "convenio_nao_aderente",
            f"O município {lugar} NÃO tem convênio com a NFS-e Nacional no ambiente de produção. "
            "As notas seriam rejeitadas (E0037). Confirme a adesão com a prefeitura.",
            TELA_PARAMETROS,
        )
    if resultado.aderente is not True:
        return Bloqueio(
            "convenio_indefinido",
            f"A consulta não deixou claro se o município {lugar} aderiu à NFS-e Nacional em "
            "produção. Tente novamente mais tarde ou confirme com a prefeitura.",
            TELA_PARAMETROS,
        )
    if resultado.data_ativacao:
        try:
            ativacao = dt.date.fromisoformat(str(resultado.data_ativacao)[:10])
        except ValueError:
            return Bloqueio(
                "convenio_data_ilegivel",
                f"Não foi possível entender a data de ativação do convênio do município {lugar} "
                f"({resultado.data_ativacao}). Confirme com a prefeitura.",
                TELA_PARAMETROS,
            )
        if ativacao > hoje:
            return Bloqueio(
                "convenio_ainda_nao_vigente",
                f"O convênio do município {lugar} só passa a valer em {ativacao:%d/%m/%Y}. "
                "Até lá as notas seriam rejeitadas.",
                TELA_PARAMETROS,
            )
    return None


def sem_consulta(motivo):
    """Pendência para quando a consulta ao vivo do convênio não pôde ser feita."""
    return Bloqueio(
        "convenio_nao_verificado",
        f"Não foi possível confirmar agora o convênio do município na produção: {motivo} "
        "A troca só é feita com o convênio confirmado; tente novamente em alguns minutos.",
        TELA_PARAMETROS,
    )


def _data(momento):
    return timezone.localtime(momento).strftime("%d/%m/%Y")
