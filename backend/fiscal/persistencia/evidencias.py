"""Evidências do que foi enviado e recebido (DPS, respostas brutas, pedidos de evento).

A DPS assinada é gravada **antes** do `POST`: se o processo cair depois do envio, é ela que
permite reconciliar sem reenviar. Por isso a gravação é confirmada na hora e nada é
sobrescrito: conteúdo diferente para a mesma tentativa vira uma nova versão.
"""

import hashlib
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max
from freedfe.nfse.evidencias import ArmazenamentoEvidencias

from fiscal.persistencia.modelos import EvidenciaFiscal


class ArmazenamentoEvidenciasPostgres(ArmazenamentoEvidencias):
    """Guarda cada evidência numa linha de `EvidenciaFiscal`; a referência devolvida é opaca."""

    def gravar_dps(self, id_dps, mes, tentativa, sufixo, conteudo):
        """Grava a DPS enviada (`dps.xml`) ou a resposta bruta (`resposta.json`)."""
        sha = hashlib.sha256(conteudo).hexdigest()
        base = {"tipo": EvidenciaFiscal.Tipo.DPS, "id_dps": id_dps, "tentativa": tentativa}
        with transaction.atomic():
            existentes = EvidenciaFiscal.objects.select_for_update().filter(sufixo=sufixo, **base)
            for existente in existentes:
                if existente.sha256 == sha:
                    return existente.referencia  # reexecução depois de uma queda
            versao = (existentes.aggregate(m=Max("versao"))["m"] or 0) + 1
            referencia = f"dps/{id_dps}/{tentativa}/{sufixo}" + (f"#{versao}" if versao > 1 else "")
            try:
                with transaction.atomic():
                    EvidenciaFiscal.objects.create(
                        referencia=referencia,
                        mes=mes,
                        sufixo=sufixo,
                        versao=versao,
                        conteudo=conteudo,
                        sha256=sha,
                        **base,
                    )
            except IntegrityError:
                # Outra execução gravou a mesma referência entre a leitura e a escrita.
                return self.gravar_dps(id_dps, mes, tentativa, sufixo, conteudo)
            return referencia

    def gravar_evento(self, chave, tipo_evento, mes, sufixo, conteudo):
        """Grava o pedido de evento (`pedido.xml`) ou a resposta; repetições viram novas linhas."""
        referencia = f"evento/{chave}/{tipo_evento}/{uuid.uuid4().hex}/{sufixo}"
        EvidenciaFiscal.objects.create(
            referencia=referencia,
            tipo=EvidenciaFiscal.Tipo.EVENTO,
            chave=chave,
            tipo_evento=tipo_evento,
            mes=mes,
            sufixo=sufixo,
            conteudo=conteudo,
            sha256=hashlib.sha256(conteudo).hexdigest(),
        )
        return referencia

    @staticmethod
    def ler(referencia):
        """Conteúdo de uma evidência, conferido contra o hash gravado."""
        linha = EvidenciaFiscal.objects.get(referencia=referencia)
        conteudo = bytes(linha.conteudo)
        if hashlib.sha256(conteudo).hexdigest() != linha.sha256:
            raise ValueError(f"A evidência {referencia} não confere com o hash gravado.")
        return conteudo
