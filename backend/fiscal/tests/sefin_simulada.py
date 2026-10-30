"""Sefin Nacional simulada: o transporte HTTP da freedfe trocado por um servidor em memória.

Nada sai para a rede. Os testes da emissão usam isto no lugar do `TransporteRest` real; a
biblioteca roda inteira (montagem e assinatura da DPS, envio, reconciliação, eventos) contra
respostas fictícias, e os testes conferem o que **chegou** à Sefin (`posts_de_emissao`).

Comportamentos configuráveis (`roteiro_emissao`, `fora_do_ar`, `cancelamento_recusado`)
cobrem timeout, 5xx, rejeição, falha depois de processar, prazo de cancelamento vencido etc.
Todos os dados são fictícios.
"""

import datetime as dt
import json
import re
from collections import deque
from urllib.parse import urlsplit

from freedfe.excecoes import ComunicacaoErro
from freedfe.nfse.envelope import comprimir_b64, descomprimir_b64
from freedfe.transporte import RespostaHttp, TransporteRest
from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
_CHAVE = r"[0-9]{50}"


def _q(nome):
    return f"{{{NS}}}{nome}"


def _achar(no, nome):
    if no is None:
        return None
    return next(iter(no.iter(_q(nome))), None)


def _texto(no, nome):
    achado = _achar(no, nome)
    return achado.text if achado is not None else None


def _json(status, dados):
    return RespostaHttp(status=status, corpo=json.dumps(dados).encode())


def _rejeicao(status, *erros):
    return _json(
        status,
        {"erros": [{"codigo": codigo, "descricao": descricao} for codigo, descricao in erros]},
    )


class SefinSimulada(TransporteRest):
    """Servidor fictício da Sefin Nacional (emissão, consulta de DPS/NFS-e e eventos)."""

    def __init__(self):
        self.chamadas = []  # (método, caminho) de tudo o que a biblioteca pediu
        self.posts_de_emissao = []  # Id da DPS de cada POST /nfse que chegou
        self.roteiro_emissao = deque()  # respostas forçadas, uma por POST /nfse
        self.fora_do_ar = False  # toda chamada falha com erro de rede
        self.cancelamento_recusado = None  # (código, descrição) para recusar o cancelamento
        self.nfses = {}  # chave -> bytes do XML
        self.dps_para_chave = {}
        self.eventos = {}  # chave -> [bytes do XML]
        self._contador = {}  # emitente -> último número de NFS-e
        self.agora = dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC)

    # -- roteiro ------------------------------------------------------------------

    def proximas(self, *comportamentos):
        """Define o que acontece nos próximos POSTs de emissão.

        Cada item é "ok", "timeout" (cai antes de processar), "cai_depois_de_processar",
        "5xx" ou `("rejeitar", [(código, descrição), ...])`.
        """
        self.roteiro_emissao.extend(comportamentos)

    @property
    def total_de_posts(self):
        return len(self.posts_de_emissao)

    # -- transporte ---------------------------------------------------------------

    def requisitar(self, metodo, url, corpo=None, cabecalhos=None, timeout=None):
        caminho = urlsplit(url).path
        self.chamadas.append((metodo, caminho))
        if self.fora_do_ar:
            raise ComunicacaoErro("Sefin fora do ar (simulado).")
        if metodo == "POST" and re.search(r"/nfse$", caminho):
            return self._emitir(corpo)
        if metodo in ("HEAD", "GET") and (m := re.search(r"/dps/(DPS[0-9A-Z]+)$", caminho)):
            return self._dps(metodo, m.group(1))
        if metodo == "POST" and (m := re.search(rf"/nfse/({_CHAVE})/eventos$", caminho)):
            return self._registrar_evento(m.group(1), corpo)
        if metodo == "GET" and (m := re.search(rf"/nfse/({_CHAVE})/eventos", caminho)):
            return self._listar_eventos(m.group(1))
        if metodo == "GET" and (m := re.search(rf"/nfse/({_CHAVE})$", caminho)):
            return self._consultar(m.group(1))
        return _rejeicao(404, ("E9999", f"Rota não simulada: {metodo} {caminho}"))

    # -- emissão ------------------------------------------------------------------

    def _emitir(self, corpo):
        dps_xml = descomprimir_b64(json.loads(corpo)["dpsXmlGZipB64"])
        dps = etree.fromstring(dps_xml)
        inf = _achar(dps, "infDPS")
        id_dps = inf.get("Id")
        self.posts_de_emissao.append(id_dps)

        comportamento = self.roteiro_emissao.popleft() if self.roteiro_emissao else "ok"
        if comportamento == "timeout":
            self.fora_do_ar = True
            raise ComunicacaoErro("Tempo esgotado esperando a Sefin (simulado).")
        if comportamento == "5xx":
            return _rejeicao(503, ("HTTP503", "Serviço indisponível (simulado)."))
        if isinstance(comportamento, tuple) and comportamento[0] == "rejeitar":
            return _rejeicao(400, *comportamento[1])

        if id_dps in self.dps_para_chave:
            return _rejeicao(
                409, ("E0014", f"Já existe NFS-e para a DPS {id_dps} (número repetido).")
            )
        substituida = _texto(inf, "chSubstda")
        if substituida and substituida not in self.nfses:
            return _rejeicao(400, ("E0841", "A NFS-e a substituir não existe."))

        chave, xml = self._gerar_nfse(dps, id_dps)
        self.nfses[chave] = xml
        self.dps_para_chave[id_dps] = chave
        if substituida:
            self._registrar_substituicao(substituida, chave)
        if comportamento == "cai_depois_de_processar":
            self.fora_do_ar = True
            raise ComunicacaoErro("A conexão caiu depois do envio (simulado).")
        return _json(201, {"chaveAcesso": chave, "nfseXmlGZipB64": comprimir_b64(xml)})

    def _gerar_nfse(self, dps, id_dps):
        municipio, tipo, inscricao = id_dps[3:10], id_dps[10], id_dps[11:25]
        numero = self._contador.get(inscricao, 0) + 1
        self._contador[inscricao] = numero
        aamm = self.agora.strftime("%y%m")
        chave = f"{municipio}2{tipo}{inscricao}{numero:013d}{aamm}{numero:09d}0"
        raiz = etree.Element(_q("NFSe"), nsmap={None: NS}, versao="1.01")
        inf = etree.SubElement(raiz, _q("infNFSe"), Id=f"NFS{chave}")
        etree.SubElement(inf, _q("xLocEmi")).text = "Município Fictício"
        etree.SubElement(inf, _q("nNFSe")).text = str(numero)
        etree.SubElement(inf, _q("dhProc")).text = self.agora.isoformat()
        emit = etree.SubElement(inf, _q("emit"))
        etree.SubElement(emit, _q("CNPJ")).text = inscricao
        etree.SubElement(emit, _q("xNome")).text = "EMPRESA DE TESTE LTDA"
        valores = etree.SubElement(inf, _q("valores"))
        etree.SubElement(valores, _q("vLiq")).text = _texto(dps, "vServ") or "0.00"
        inf.append(dps)  # a DPS segue embutida na NFS-e, como na Sefin real
        return chave, etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")

    # -- consultas ----------------------------------------------------------------

    def _dps(self, metodo, id_dps):
        chave = self.dps_para_chave.get(id_dps)
        if chave is None:
            return _rejeicao(404, ("E0404", "DPS não encontrada."))
        return (
            RespostaHttp(status=200, corpo=b"")
            if metodo == "HEAD"
            else _json(200, {"chaveAcesso": chave})
        )

    def _consultar(self, chave):
        xml = self.nfses.get(chave)
        if xml is None:
            return _rejeicao(404, ("E0404", "NFS-e não encontrada."))
        return _json(200, {"chaveAcesso": chave, "nfseXmlGZipB64": comprimir_b64(xml)})

    # -- eventos ------------------------------------------------------------------

    def _registrar_evento(self, chave, corpo):
        pedido = etree.fromstring(
            descomprimir_b64(json.loads(corpo)["pedidoRegistroEventoXmlGZipB64"])
        )
        if chave not in self.nfses:
            return _rejeicao(404, ("E0404", "NFS-e não encontrada."))
        if any(self._tipo(e) in ("101101", "105102") for e in self.eventos.get(chave, [])):
            return _rejeicao(409, ("E0840", "A NFS-e já está cancelada ou substituída."))
        if self.cancelamento_recusado:
            codigo, descricao = self.cancelamento_recusado
            return _rejeicao(400, (codigo, descricao))
        tipo = next(
            e.tag.split("}")[1][1:]
            for e in _achar(pedido, "infPedReg")
            if isinstance(e.tag, str) and re.fullmatch(r"\{.*\}e[0-9]{6}", e.tag)
        )
        xml = self._evento(chave, tipo, _texto(pedido, "xMotivo") or "")
        self.eventos.setdefault(chave, []).append(xml)
        return _json(201, {"eventoXmlGZipB64": comprimir_b64(xml)})

    def _registrar_substituicao(self, substituida, substituta):
        xml = self._evento(substituida, "105102", "Substituída", substituta=substituta)
        self.eventos.setdefault(substituida, []).append(xml)

    def _evento(self, chave, tipo, motivo, substituta=None):
        sequencia = len(self.eventos.get(chave, [])) + 1
        raiz = etree.Element(_q("evento"), nsmap={None: NS}, versao="1.01")
        inf = etree.SubElement(raiz, _q("infEvento"), Id=f"EVT{chave}{tipo}{sequencia:03d}")
        etree.SubElement(inf, _q("nSeqEvento")).text = str(sequencia)
        etree.SubElement(inf, _q("dhProc")).text = self.agora.isoformat()
        pedido = etree.SubElement(inf, _q("pedRegEvento"))
        pedido_inf = etree.SubElement(pedido, _q("infPedReg"))
        etree.SubElement(pedido_inf, _q("dhEvento")).text = self.agora.isoformat()
        etree.SubElement(pedido_inf, _q("chNFSe")).text = chave
        corpo = etree.SubElement(pedido_inf, _q(f"e{tipo}"))
        etree.SubElement(corpo, _q("xDesc")).text = {
            "101101": "Cancelamento de NFS-e",
            "105102": "Cancelamento de NFS-e por Substituicao",
        }.get(tipo, "Evento")
        etree.SubElement(corpo, _q("xMotivo")).text = motivo
        if substituta:
            etree.SubElement(corpo, _q("chSubstituta")).text = substituta
        return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")

    @staticmethod
    def _tipo(xml):
        for elemento in etree.fromstring(xml).iter():
            if isinstance(elemento.tag, str) and re.fullmatch(r"\{.*\}e[0-9]{6}", elemento.tag):
                return elemento.tag.split("}")[1][1:]
        return None

    def _listar_eventos(self, chave):
        xmls = self.eventos.get(chave, [])
        if not xmls:
            return _rejeicao(404, ("E0404", "Sem eventos."))
        return _json(200, {"eventos": [{"arquivoXml": comprimir_b64(x)} for x in xmls]})
