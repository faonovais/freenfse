"""XML fictício de NFS-e e de eventos, no formato que a freedfe lê (dados inventados)."""

import datetime as dt

from lxml import etree

from fiscal.tests.sefin_simulada import NS, SefinSimulada


def _q(nome):
    return f"{{{NS}}}{nome}"


def dps_ficticia(id_dps, *, valor="100.00", tomador_cnpj="11444777000161", serie="900"):
    """Elemento `DPS` mínimo, suficiente para a Sefin simulada e para o extrator da biblioteca."""
    raiz = etree.Element(_q("DPS"), nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(raiz, _q("infDPS"), Id=id_dps)
    etree.SubElement(inf, _q("dhEmi")).text = "2026-11-02T11:55:00-03:00"
    etree.SubElement(inf, _q("serie")).text = serie
    toma = etree.SubElement(inf, _q("toma"))
    etree.SubElement(toma, _q("CNPJ")).text = tomador_cnpj
    etree.SubElement(toma, _q("xNome")).text = "TOMADOR FICTICIO LTDA"
    valores = etree.SubElement(inf, _q("valores"))
    servico = etree.SubElement(valores, _q("vServPrest"))
    etree.SubElement(servico, _q("vServ")).text = valor
    return raiz


def nfse_ficticia(id_dps, **opcoes):
    """`(chave, xml)` de uma NFS-e fictícia gerada para a DPS informada."""
    sefin = SefinSimulada()
    sefin._contador[id_dps[11:25]] = int(id_dps[30:45]) - 1  # nNFSe segue o nDPS
    return sefin._gerar_nfse(dps_ficticia(id_dps, **opcoes), id_dps)


def evento_ficticio(chave, tipo="101101", motivo="Cancelamento de teste do freenfse"):
    """XML de evento fictício (por padrão, cancelamento)."""
    return SefinSimulada()._evento(chave, tipo, motivo)


def agora():
    return dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC)
