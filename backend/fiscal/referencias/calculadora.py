"""Baixa a classificação tributária (cClassTrib) dos dados abertos da calculadora do IBS/CBS.

As regras E0859/E0860/E0958/E0960/E0961 do Anexo VI mandam consultar a calculadora para saber se a
classificação do serviço exige o grupo de IBS/CBS (`ind_gIBSCBS`) e se vale para NFS-e. O mesmo
caminho da URL citada no anexo é público em `piloto-cbs.tributos.gov.br` (RFB/CGIBS):

- `.../cbs-ibs?data=AAAA-MM-DD`: classificações **vigentes** na data e os DF-e que as aceitam;
- `.../cbs-ibs/NFSE/<cClassTrib>?data=AAAA-MM-DD`: `exigeGrupoIbsCbs` e se vale para NFS-e.

Cuidados com o serviço (observados na prática): sob rajada, o firewall responde **HTTP 200 com uma
página HTML "Request Rejected"**, então toda resposta é validada como JSON, as chamadas são
espaçadas e a falha vira nova tentativa; nunca se grava resposta inválida. A fonte não informa
início/fim de vigência, só dá a lista de uma data: as datas são **descobertas** amostrando o
período e refinando (busca binária) onde a lista muda.
"""

import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.request

URL_BASE = (
    "https://piloto-cbs.tributos.gov.br/servico/calculadora-consumo/api/calculadora/dados-abertos/"
)
TIPO_DFE_NFSE = 91
TENTATIVAS = 4
ESPERA_ENTRE_CHAMADAS = 0.6
ESPERA_DA_PRIMEIRA_NOVA_TENTATIVA = 4.0


class ErroDeFonte(Exception):
    """A fonte oficial não respondeu de forma utilizável (rede, firewall ou conteúdo inesperado)."""


def buscar_na_internet(url):
    """GET com tempo limite; devolve o corpo em bytes."""
    pedido = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:  # noqa: S310 - https fixo
            return resposta.read()
    except (urllib.error.URLError, OSError) as erro:
        raise ErroDeFonte(f"Falha ao consultar {url}: {erro}") from None


class Calculadora:
    """Cliente dos dados abertos, com validação de JSON, espaçamento e nova tentativa."""

    def __init__(
        self, *, buscar=buscar_na_internet, pausa=time.sleep, espera=ESPERA_ENTRE_CHAMADAS
    ):
        """`buscar` e `pausa` são injetáveis: os testes não usam rede nem esperam de verdade."""
        self._buscar = buscar
        self._pausa = pausa
        self._espera = espera
        self.chamadas = 0
        self.amostras = {}

    def _json(self, caminho):
        url = URL_BASE + caminho
        atraso = ESPERA_DA_PRIMEIRA_NOVA_TENTATIVA
        ultimo = "sem resposta"
        for tentativa in range(TENTATIVAS):
            self._pausa(self._espera)
            self.chamadas += 1
            try:
                corpo = self._buscar(url)
                return json.loads(corpo.decode("utf-8")), corpo
            except (ErroDeFonte, UnicodeDecodeError, json.JSONDecodeError) as erro:
                ultimo = str(erro)[:120] or type(erro).__name__
            if tentativa < TENTATIVAS - 1:
                self._pausa(atraso)
                atraso *= 2
        raise ErroDeFonte(
            f"Sem resposta JSON válida de {url} após {TENTATIVAS} tentativas ({ultimo})."
        )

    def versao(self):
        """Versão do aplicativo e da base de dados da calculadora (proveniência do arquivo)."""
        dados, _ = self._json("versao")
        return {
            campo: dados.get(campo)
            for campo in ("versaoApp", "versaoDb", "descricaoVersaoDb", "dataVersaoDb", "ambiente")
        }

    def classificacoes_em(self, data):
        """`{codigo: item}` das classificações vigentes na data (lista oficial)."""
        dados, corpo = self._json(f"classificacoes-tributarias/cbs-ibs?data={data.isoformat()}")
        if not isinstance(dados, list) or not dados:
            raise ErroDeFonte(
                f"A lista de classificações de {data} veio vazia ou em outro formato."
            )
        self.amostras[data.isoformat()] = hashlib.sha256(corpo).hexdigest()
        return {item["codigo"]: item for item in dados}

    def indicador_nfse(self, codigo, data):
        """`(valido_para_nfse, exige_grupo_ibs_cbs)` de uma classificação numa data."""
        dados, _ = self._json(
            f"classificacoes-tributarias/cbs-ibs/NFSE/{codigo}?data={data.isoformat()}"
        )
        valido, exige = dados.get("validoParaSiglaDfeInformado"), dados.get("exigeGrupoIbsCbs")
        if not isinstance(valido, bool) or not isinstance(exige, bool):
            raise ErroDeFonte(f"Resposta sem os indicadores esperados para {codigo} em {data}.")
        return valido, exige


def _amostras_de_datas(inicio, fim):
    """O dia 1º de cada mês entre `inicio` e `fim`, mais as duas pontas."""
    datas = {inicio, fim}
    atual = inicio.replace(day=1)
    while atual <= fim:
        if atual >= inicio:
            datas.add(atual)
        atual = (atual.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return sorted(datas)


def _primeiro_dia_presente(calculadora, codigo, ausente, presente):
    """Menor data em `[ausente+1, presente]` em que a classificação está vigente (busca binária)."""
    while (presente - ausente).days > 1:
        meio = ausente + (presente - ausente) // 2
        if codigo in calculadora.classificacoes_em(meio):
            presente = meio
        else:
            ausente = meio
    return presente


def _ultimo_dia_presente(calculadora, codigo, presente, ausente):
    """Maior data em `[presente, ausente-1]` em que a classificação está vigente."""
    while (ausente - presente).days > 1:
        meio = presente + (ausente - presente) // 2
        if codigo in calculadora.classificacoes_em(meio):
            presente = meio
        else:
            ausente = meio
    return presente


def montar_tabela(calculadora, inicio, fim):
    """Tabela de classificações com vigência e indicadores de NFS-e, pesquisada em `[inicio, fim]`.

    Levanta `ErroDeFonte` se uma classificação sumir e voltar (vigência não contígua) ou se o
    indicador de NFS-e mudar dentro da vigência: esses casos pedem decisão humana.
    """
    datas = _amostras_de_datas(inicio, fim)
    listas = {data: calculadora.classificacoes_em(data) for data in datas}
    todos = sorted({codigo for lista in listas.values() for codigo in lista})
    classificacoes = []
    for codigo in todos:
        presencas = [codigo in listas[data] for data in datas]
        primeira, ultima = presencas.index(True), len(presencas) - 1 - presencas[::-1].index(True)
        if not all(presencas[primeira : ultima + 1]):
            raise ErroDeFonte(f"A classificação {codigo} sai e volta a vigorar: confira a fonte.")
        vigencia_inicio, vigencia_fim = datas[primeira], datas[ultima]
        if primeira > 0:
            vigencia_inicio = _primeiro_dia_presente(
                calculadora, codigo, datas[primeira - 1], datas[primeira]
            )
        if ultima < len(datas) - 1:
            vigencia_fim = _ultimo_dia_presente(
                calculadora, codigo, datas[ultima], datas[ultima + 1]
            )
        item = listas[datas[ultima]][codigo]
        aceita_nfse = any(t.get("tipo") == TIPO_DFE_NFSE for t in item["tiposDfeClassificacao"])
        registro = {
            "codigo": codigo,
            "descricao": item["descricao"],
            "vigencia_inicio": vigencia_inicio.isoformat(),
            "vigencia_fim": None if ultima == len(datas) - 1 else vigencia_fim.isoformat(),
            "aceita_nfse": aceita_nfse,
            "exige_grupo_ibs_cbs": None,
        }
        if aceita_nfse:
            consultas = {vigencia_inicio, vigencia_fim}
            indicadores = {calculadora.indicador_nfse(codigo, d) for d in sorted(consultas)}
            if len(indicadores) != 1:
                raise ErroDeFonte(f"O indicador de NFS-e de {codigo} muda dentro da vigência.")
            valido, exige = indicadores.pop()
            registro["aceita_nfse"] = valido
            registro["exige_grupo_ibs_cbs"] = exige if valido else None
        classificacoes.append(registro)
    return classificacoes
