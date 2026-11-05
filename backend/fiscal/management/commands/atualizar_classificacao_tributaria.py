"""Regrava a classificação tributária versionada com os dados abertos da calculadora."""

import datetime as dt
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fiscal.referencias import anexos_rtc, calculadora

PASTA_DOS_DADOS = Path(__file__).resolve().parents[2] / "referencias" / "dados"


def _data(texto):
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        raise CommandError(f"Data inválida: {texto!r}. Use AAAA-MM-DD.") from None


class Command(BaseCommand):
    """Consulta a calculadora oficial (rede) e grava `classificacao_tributaria.json`."""

    help = (
        "Baixa as classificações tributárias (cClassTrib) dos dados abertos da calculadora do "
        "IBS/CBS, descobre a vigência de cada uma e grava fiscal/referencias/dados/"
        "classificacao_tributaria.json. Leva alguns minutos (chamadas espaçadas por causa do "
        "firewall da fonte)."
    )

    def add_arguments(self, parser):
        """Período pesquisado e pasta de saída."""
        parser.add_argument(
            "--de", default="2026-01-01", help="Início da pesquisa (padrão: 2026-01-01)."
        )
        parser.add_argument(
            "--ate", default="2033-12-31", help="Fim da pesquisa (padrão: 2033-12-31)."
        )
        parser.add_argument("--saida", help="Pasta de saída (padrão: a versionada).")

    def handle(self, *args, **opcoes):
        """Monta a tabela, grava o JSON e imprime o SHA-256 e as contagens (para o LEIAME)."""
        inicio, fim = _data(opcoes["de"]), _data(opcoes["ate"])
        if fim <= inicio:
            raise CommandError("--ate precisa ser depois de --de.")
        cliente = calculadora.Calculadora()
        try:
            versao = cliente.versao()
            tabela = calculadora.montar_tabela(cliente, inicio, fim)
        except calculadora.ErroDeFonte as erro:
            raise CommandError(str(erro)) from erro
        saida = Path(opcoes["saida"] or PASTA_DOS_DADOS)
        saida.mkdir(parents=True, exist_ok=True)
        origem = {
            "documento": "Calculadora do IBS/CBS (RFB/CGIBS): dados abertos, classificações",
            "url": calculadora.URL_BASE + "classificacoes-tributarias/cbs-ibs",
            "obtido_em": dt.date.today().isoformat(),
            "periodo_pesquisado": [inicio.isoformat(), fim.isoformat()],
            "calculadora": versao,
            "sha256_das_listas": dict(sorted(cliente.amostras.items())),
        }
        sha = anexos_rtc.gravar_json(
            {"origem": origem, "classificacoes": tabela}, saida / "classificacao_tributaria.json"
        )
        escrever = self.stdout.write
        escrever(f"classificacao_tributaria.json: SHA-256 {sha}")
        escrever(f"Calculadora: {versao}")
        nfse = [c for c in tabela if c["aceita_nfse"]]
        escrever(
            f"{len(tabela)} classificações; {len(nfse)} valem para NFS-e "
            f"({sum(1 for c in nfse if c['exige_grupo_ibs_cbs'])} exigem o grupo IBS/CBS); "
            f"{cliente.chamadas} chamadas à fonte."
        )
        encerradas = [c["codigo"] for c in tabela if c["vigencia_fim"]]
        escrever(f"Com fim de vigência: {', '.join(encerradas) or 'nenhuma'}")
