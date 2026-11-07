"""Gera as tabelas versionadas a partir dos anexos técnicos oficiais da NFS-e (NT 009)."""

import datetime as dt
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fiscal.referencias import anexos_rtc
from fiscal.referencias.xlsx import ErroDePlanilha, Planilha

PASTA_DOS_DADOS = Path(__file__).resolve().parents[2] / "referencias" / "dados"
URL_BASE = "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"


class Command(BaseCommand):
    """Lê os `.xlsx` oficiais baixados e regrava os dois JSON de incidência e de INDOP."""

    help = (
        "Gera fiscal/referencias/dados/localidade_incidencia.json (Anexo VI) e "
        "correlacao_indop.json (Anexo VIII) a partir dos .xlsx baixados de gov.br/nfse "
        "(Biblioteca > Documentação técnica > RTC). Sem rede: baixe os arquivos antes."
    )

    def add_arguments(self, parser):
        """Recebe os dois anexos e, opcionalmente, a data da obtenção e a pasta de saída."""
        parser.add_argument(
            "--anexo-vi", required=True, help="anexovi-leiautesrn_rtc_ibscbs-*.xlsx"
        )
        parser.add_argument(
            "--anexo-viii", required=True, help="Anexo VIII (tabela de correlação)."
        )
        parser.add_argument("--obtido-em", help="Data do download (AAAA-MM-DD); padrão: hoje.")
        parser.add_argument("--saida", help="Pasta de saída (padrão: a versionada).")

    def _origem(self, caminho, documento, obtido_em):
        caminho = Path(caminho)
        return {
            "documento": documento,
            "arquivo": caminho.name,
            "url": URL_BASE + caminho.name,
            "sha256": anexos_rtc.sha256_do_arquivo(caminho),
            "obtido_em": obtido_em,
        }

    def handle(self, *args, **opcoes):
        """Extrai as duas tabelas e imprime o SHA-256 de cada arquivo gerado (para o LEIAME)."""
        obtido_em = opcoes["obtido_em"] or dt.date.today().isoformat()
        try:
            dt.date.fromisoformat(obtido_em)
        except ValueError:
            raise CommandError("Use --obtido-em no formato AAAA-MM-DD.") from None
        saida = Path(opcoes["saida"] or PASTA_DOS_DADOS)
        saida.mkdir(parents=True, exist_ok=True)
        try:
            vi = Planilha(opcoes["anexo_vi"])
            viii = Planilha(opcoes["anexo_viii"])
            localidade = anexos_rtc.extrair_localidade_incidencia(vi)
            correlacao = anexos_rtc.extrair_correlacao_indop(viii)
        except (ErroDePlanilha, OSError) as erro:
            raise CommandError(str(erro)) from erro
        origem_vi = self._origem(
            opcoes["anexo_vi"],
            "NT SE/CGNFS-e 009 — Anexo VI (Leiaute SRN), aba MUN.INCID_INFO.SERV.",
            obtido_em,
        )
        origem_viii = self._origem(
            opcoes["anexo_viii"],
            "NT SE/CGNFS-e 009 — Anexo VIII (correlação item × NBS × INDOP × cClassTrib)",
            obtido_em,
        )
        escrever = self.stdout.write
        for nome, origem, conteudo in (
            ("localidade_incidencia.json", origem_vi, {"regras": localidade}),
            ("correlacao_indop.json", origem_viii, correlacao),
        ):
            sha = anexos_rtc.gravar_json({"origem": origem, **conteudo}, saida / nome)
            escrever(f"{nome}: SHA-256 {sha}")
            escrever(f"  origem: {origem['arquivo']} (SHA-256 {origem['sha256']})")
        contagem = {}
        for regra in localidade.values():
            contagem[regra] = contagem.get(regra, 0) + 1
        escrever(
            f"Serviços na aba de incidência: {len(localidade)} {dict(sorted(contagem.items()))}"
        )
        pares = sum(len(por_nbs) for por_nbs in correlacao["itens"].values())
        escrever(
            f"Anexo VIII: {len(correlacao['itens'])} itens da LC 116 e {pares} pares item × NBS"
        )
