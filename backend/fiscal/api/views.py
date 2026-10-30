"""Views da configuração fiscal: parâmetros, certificado, logo e identidade da empresa."""

import hashlib

from django.core.exceptions import ValidationError as ErroDjango
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.permissions import PermissaoPorOperacao, QualquerVinculado
from core.models import LogAuditoria
from core.services import auditoria
from fiscal import logo as logos
from fiscal.models import Certificado, LogoEmpresa, ParametrosFiscais
from fiscal.services import certificado as servico_certificado
from fiscal.services import parametros as servico_parametros
from fiscal.services.vencimento import faixa_de

from .serializers import (
    CertificadoSerializer,
    EntradaDeParametros,
    ParametrosFiscaisSerializer,
    opcoes_de_parametros,
)


def _resposta_de_parametros(parametros, codigo=status.HTTP_200_OK):
    dados = ParametrosFiscaisSerializer(parametros).data
    return Response({**dados, "opcoes": opcoes_de_parametros()}, status=codigo)


class ParametrosView(APIView):
    """Parâmetros fiscais da empresa (consulta e alteração)."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "config.consultar", "patch": "config.editar"}

    def get(self, request):
        """Devolve os parâmetros (criados com os padrões na primeira consulta)."""
        return _resposta_de_parametros(ParametrosFiscais.obter())

    def patch(self, request):
        """Altera os parâmetros. Trocar para produção exige `confirmar_producao: true`."""
        entrada = EntradaDeParametros(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = dict(entrada.validated_data)
        confirmar = dados.pop("confirmar_producao", False)
        try:
            parametros = servico_parametros.atualizar_parametros(
                request=request, dados=dados, confirmar_producao=confirmar
            )
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.message_dict) from None
        except servico_parametros.ProducaoSemConfirmacao:
            return Response(
                {
                    "codigo": "confirmacao_necessaria",
                    "detalhe": (
                        "Trocar para produção faz as próximas notas terem valor fiscal. "
                        "Confirme a troca para continuar."
                    ),
                    "ambiente": ["Confirme a troca para o ambiente de produção."],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _resposta_de_parametros(parametros)


class VerificarConvenioView(APIView):
    """Consulta o convênio do município emissor no ambiente nacional."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "config.editar"}

    def post(self, request):
        """Verifica e guarda o resultado com a data."""
        try:
            parametros = servico_parametros.verificar_convenio(request=request)
        except servico_parametros.ErroDeVerificacao as erro:
            return Response(
                {"codigo": "convenio_nao_verificado", "detalhe": str(erro)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servico_parametros.ErroDeConsultaExterna as erro:
            return Response(
                {"codigo": "convenio_indisponivel", "detalhe": str(erro)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return _resposta_de_parametros(parametros)


def _verdadeiro(valor):
    return str(valor).lower() in ("true", "1", "on", "sim")


class CertificadoView(APIView):
    """Certificado A1 da empresa: envio (multipart), consulta de metadados e remoção."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "get": "config.consultar",
        "post": "config.editar",
        "delete": "config.editar",
    }
    parser_classes = [MultiPartParser]

    def get(self, request):
        """Metadados do certificado (titular, CNPJ, validade); nunca o arquivo nem a senha."""
        certificado = Certificado.objects.first()
        if certificado is None:
            return Response({"existe": False})
        return Response({"existe": True, **CertificadoSerializer(certificado).data})

    def post(self, request):
        """Valida e guarda o certificado: campos `arquivo` (.pfx), `senha` e `mesma_raiz`."""
        arquivo = request.FILES.get("arquivo")
        if arquivo is not None and arquivo.size > servico_certificado.LIMITE_ARQUIVO_BYTES:
            conteudo = b"x" * (servico_certificado.LIMITE_ARQUIVO_BYTES + 1)
        else:
            conteudo = arquivo.read() if arquivo is not None else b""
        try:
            certificado = servico_certificado.enviar_certificado(
                request=request,
                empresa=request.empresa,
                arquivo=conteudo,
                senha=request.data.get("senha", ""),
                mesma_raiz=_verdadeiro(request.data.get("mesma_raiz", "")),
            )
        except servico_certificado.ErroDeCertificado as erro:
            return Response(
                {"codigo": "certificado_recusado", "detalhe": str(erro)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"existe": True, **CertificadoSerializer(certificado).data},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        """Remove o certificado guardado."""
        servico_certificado.remover_certificado(request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _cabecalhos_do_logo(resposta, sha256):
    resposta["ETag"] = f'"{sha256}"'
    resposta["Cache-Control"] = "private, no-cache"
    resposta["X-Content-Type-Options"] = "nosniff"
    # Mesmo que alguém abra o arquivo direto, nada executa: sem script e em caixa isolada.
    resposta["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return resposta


class LogoView(APIView):
    """Logo da empresa por tema (`claro` ou `escuro`)."""

    parser_classes = [MultiPartParser]
    permissao_requerida = {"put": "config.editar", "delete": "config.editar"}

    def get_permissions(self):
        """Libera a leitura a qualquer vinculado; a alteração exige `config.editar`."""
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [QualquerVinculado()]
        return [PermissaoPorOperacao()]

    @staticmethod
    def _tema(valor):
        if valor not in LogoEmpresa.Tema.values:
            raise serializers.ValidationError({"tema": ["Use `claro` ou `escuro`."]})
        return valor

    def get(self, request, tema):
        """Devolve a imagem. Sem logo escuro, usa o claro; sem nenhum, 404."""
        tema = self._tema(tema)
        logo = LogoEmpresa.objects.filter(tema=tema).first()
        if logo is None and tema == LogoEmpresa.Tema.ESCURO:
            logo = LogoEmpresa.objects.filter(tema=LogoEmpresa.Tema.CLARO).first()
        if logo is None:
            return Response(
                {"detalhe": "A empresa não tem logo."}, status=status.HTTP_404_NOT_FOUND
            )
        if request.headers.get("If-None-Match") == f'"{logo.sha256}"':
            return _cabecalhos_do_logo(HttpResponse(status=304), logo.sha256)
        resposta = HttpResponse(bytes(logo.conteudo), content_type=logo.tipo_conteudo)
        return _cabecalhos_do_logo(resposta, logo.sha256)

    def put(self, request, tema):
        """Valida, sanitiza e guarda o logo do tema (campo `arquivo`, PNG ou SVG)."""
        tema = self._tema(tema)
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            raise serializers.ValidationError({"arquivo": ["Escolha o arquivo do logo."]})
        limite = max(logos.LIMITE_PNG_BYTES, logos.LIMITE_SVG_BYTES)
        if arquivo.size > limite:
            raise serializers.ValidationError(
                {"arquivo": [f"O arquivo é grande demais (máximo de {limite // 1024} KB)."]}
            )
        try:
            validado = logos.validar_logo(arquivo.read())
        except logos.ErroDeLogo as erro:
            raise serializers.ValidationError({"arquivo": [str(erro)]}) from None
        sha256 = hashlib.sha256(validado.conteudo).hexdigest()
        LogoEmpresa.objects.update_or_create(
            tema=tema,
            defaults={
                "tipo_conteudo": validado.tipo_conteudo,
                "conteudo": validado.conteudo,
                "sha256": sha256,
            },
        )
        auditoria.registrar(
            LogAuditoria.Acao.LOGO_ALTERADO,
            request=request,
            alvo=f"logo:{tema}",
            detalhes={
                "sha256": sha256,
                "tipo": validado.tipo_conteudo,
                "removidos": validado.removidos,
            },
        )
        return Response(
            {
                "tema": tema,
                "tipo_conteudo": validado.tipo_conteudo,
                "sha256": sha256,
                "removidos": validado.removidos,
            },
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, tema):
        """Remove o logo do tema."""
        tema = self._tema(tema)
        removidos, _ = LogoEmpresa.objects.filter(tema=tema).delete()
        if removidos:
            auditoria.registrar(
                LogAuditoria.Acao.LOGO_ALTERADO, request=request, alvo=f"logo:{tema}",
                detalhes={"removido": True},
            )  # fmt: skip
        return Response(status=status.HTTP_204_NO_CONTENT)


class IdentidadeView(APIView):
    """O que a interface mostra a todos sobre a empresa ativa: ambiente, logo e certificado."""

    permission_classes = [QualquerVinculado]

    def get(self, request):
        """Ambiente de emissão, versões dos logos e situação resumida do certificado."""
        parametros = ParametrosFiscais.obter()
        certificado = Certificado.objects.first()
        faixa = None
        if certificado is not None:
            faixa = faixa_de(certificado.dias_para_vencer(), certificado.vencido())
        return Response(
            {
                "ambiente": parametros.ambiente,
                "ambiente_rotulo": parametros.get_ambiente_display(),
                "logo": {logo.tema: logo.sha256 for logo in LogoEmpresa.objects.all()},
                "certificado": {
                    "existe": certificado is not None,
                    "vencido": certificado.vencido() if certificado else False,
                    "dias_para_vencer": certificado.dias_para_vencer() if certificado else None,
                    "faixa_alerta": None if faixa is None else int(faixa),
                },
            }
        )
