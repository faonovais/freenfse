"""Repositório de documentos fiscais em PostgreSQL: XML original + hash + índice consultável.

O XML é gravado exatamente como a Sefin devolveu (auditabilidade) e lido de volta conferido
contra o SHA-256 gravado: adulteração ou corrupção no banco vira erro, não um DANFSe errado.
"""

import hashlib
from collections.abc import Iterable

from django.db import transaction
from freedfe.documentos.resumo import EventoDocumento, ResumoDocumento
from freedfe.repositorio.base import RepositorioDocumentos
from freedfe.tipos import ModeloDocumento

from fiscal.persistencia.modelos import (
    DocumentoFiscal,
    EventoFiscal,
    NsuRecebido,
    XmlNaoReconhecido,
)


class DocumentoAdulteradoErro(Exception):
    """O XML guardado não confere com o hash gravado."""


def _sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


class RepositorioDocumentosPostgres(RepositorioDocumentos):
    """Repositório das NFS-e (e seus eventos) no schema da empresa ativa."""

    def armazenar(self, documentos: Iterable, sequencia: ModeloDocumento | None = None):
        """Grava os XMLs de uma só vez: ou entra tudo ou nada."""
        with transaction.atomic():
            return super().armazenar(documentos, sequencia)

    # -- consulta ----------------------------------------------------------------------

    def obter(self, modelo, chave):
        """Resumo do documento (sem aplicar eventos), se existir."""
        linha = DocumentoFiscal.objects.filter(
            modelo=ModeloDocumento.normalizar(modelo).value, chave=chave
        ).first()
        return ResumoDocumento.de_dict(linha.resumo) if linha else None

    def eventos(self, modelo, chave):
        """Eventos conhecidos da chave, na ordem em que chegaram."""
        linhas = EventoFiscal.objects.filter(
            modelo=ModeloDocumento.normalizar(modelo).value, chave=chave
        ).order_by("id")
        return [EventoDocumento.de_dict(linha.resumo) for linha in linhas]

    def ler_xml(self, resumo):
        """XML original, conferido contra o hash gravado."""
        linha = DocumentoFiscal.objects.get(modelo=resumo.modelo.value, chave=resumo.chave)
        xml = bytes(linha.xml)
        if _sha256(xml) != linha.sha256:
            raise DocumentoAdulteradoErro(
                f"O XML da nota {resumo.chave} não confere com o hash gravado."
            )
        return xml

    def hash_do_documento(self, modelo, chave):
        """SHA-256 gravado do XML, ou `None` se o documento não existe."""
        return (
            DocumentoFiscal.objects.filter(
                modelo=ModeloDocumento.normalizar(modelo).value, chave=chave
            )
            .values_list("sha256", flat=True)
            .first()
        )

    def _resumos(self, modelo):
        linhas = DocumentoFiscal.objects.filter(modelo=ModeloDocumento.normalizar(modelo).value)
        return [ResumoDocumento.de_dict(linha.resumo) for linha in linhas]

    def _nsus(self, modelo):
        return list(
            NsuRecebido.objects.filter(modelo=ModeloDocumento.normalizar(modelo).value).values_list(
                "nsu", flat=True
            )
        )

    # -- gravação ----------------------------------------------------------------------

    def _gravar_documento(self, resumo, xml):
        existente = (
            DocumentoFiscal.objects.select_for_update()
            .filter(modelo=resumo.modelo.value, chave=resumo.chave)
            .first()
        )
        if existente is not None and existente.xml_completo and not resumo.xml_completo:
            return  # nunca rebaixa um XML completo para um resumo
        resumo.caminho_xml = f"{resumo.modelo.value}/{resumo.chave}"
        valores = {
            "tipo_xml": resumo.tipo_xml,
            "xml_completo": resumo.xml_completo,
            "resumo": resumo.para_dict(),
            "xml": xml,
            "sha256": _sha256(xml),
            "nsu": resumo.nsu or "",
        }
        if existente is None:
            DocumentoFiscal.objects.create(
                modelo=resumo.modelo.value, chave=resumo.chave, **valores
            )
            return
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        existente.save()

    def _gravar_evento(self, evento, xml):
        identificador = evento.protocolo or evento.nsu or _sha256(xml)[:16]
        evento.caminho_xml = f"{evento.modelo.value}/eventos/{evento.chave}/{identificador}"
        EventoFiscal.objects.get_or_create(
            modelo=evento.modelo.value,
            chave=evento.chave,
            tipo_evento=evento.tipo_evento,
            identificador=identificador,
            defaults={
                "resumo": evento.para_dict(),
                "xml": xml,
                "sha256": _sha256(xml),
                "nsu": evento.nsu or "",
            },
        )

    def _gravar_nao_reconhecido(self, recebido):
        XmlNaoReconhecido.objects.create(
            nsu=recebido.nsu or "",
            esquema=(recebido.schema or "")[:120],
            xml=recebido.xml,
            sha256=_sha256(recebido.xml),
        )

    def _registrar_nsu(self, modelo, nsu):
        NsuRecebido.objects.get_or_create(modelo=ModeloDocumento.normalizar(modelo).value, nsu=nsu)

    def _confirmar(self):
        """Cada gravação já é confirmada pelo banco; nada fica pendente."""
