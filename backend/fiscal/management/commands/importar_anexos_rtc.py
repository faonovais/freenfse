"""Gera as tabelas versionadas a partir dos anexos técnicos oficiais da NFS-e (NT 009)."""

import datetime as dt
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fiscal.referencias import anexos_rtc
from fiscal.referencias.xlsx import ErroDePlanilha, Planilha

PASTA_DOS_DADOS = Path(__file__).resolve().parents[2] / "referencias" / "dados"
URL_BASE = "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"


class Command(BaseCommand):
    """Lê os `.xlsx` oficiais baixados e regrava os JSON de incidência, INDOP e local."""

    help = (
        "Gera fiscal/referencias/dados/localidade_incidencia.json (Anexo VI), "
        "correlacao_indop.json (Anexo VIII) e indop_local_fornecimento.json (Anexo VII) a partir "
        "dos .xlsx baixados de gov.br/nfse (Biblioteca > Documentação técnica > RTC). Os anexos "
        "VI e VIII vão juntos; o VII pode ser regravado sozinho. Sem rede: baixe antes."
    )

    def add_arguments(self, parser):
        """Recebe os anexos e, opcionalmente, a data da obtenção e a pasta de saída."""
        parser.add_argument("--anexo-vi", help="anexovi-leiautesrn_rtc_ibscbs-*.xlsx")
        parser.add_argument("--anexo-viii", help="Anexo VIII (tabela de correlação).")
        parser.add_argument("--anexo-vii", help="anexovii-indop_ibscbs_*.xlsx (indicadores).")
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
        """Extrai as tabelas pedidas e imprime o SHA-256 de cada arquivo gerado (para o LEIAME)."""
        obtido_em = opcoes["obtido_em"] or dt.date.today().isoformat()
        try:
            dt.date.fromisoformat(obtido_em)
        except ValueError:
            raise CommandError("Use --obtido-em no formato AAAA-MM-DD.") from None
        vi, viii, vii = opcoes["anexo_vi"], opcoes["anexo_viii"], opcoes["anexo_vii"]
        if bool(vi) != bool(viii):
            raise CommandError("Os anexos VI e VIII vão juntos: informe os dois, ou nenhum.")
        if not (vi or vii):
            raise CommandError("Informe --anexo-vi e --anexo-viii, e/ou --anexo-vii.")
        saida = Path(opcoes["saida"] or PASTA_DOS_DADOS)
        saida.mkdir(parents=True, exist_ok=True)
        try:
            if vi:
                self._gravar_vi_e_viii(vi, viii, obtido_em, saida)
            if vii:
                self._gravar_vii(vii, obtido_em, saida)
        except (ErroDePlanilha, OSError) as erro:
            raise CommandError(str(erro)) from erro

    def _gravar(self, nome, origem, conteudo, saida):
        sha = anexos_rtc.gravar_json({"origem": origem, **conteudo}, saida / nome)
        self.stdout.write(f"{nome}: SHA-256 {sha}")
        self.stdout.write(f"  origem: {origem['arquivo']} (SHA-256 {origem['sha256']})")

    def _gravar_vi_e_viii(self, caminho_vi, caminho_viii, obtido_em, saida):
        localidade = anexos_rtc.extrair_localidade_incidencia(Planilha(caminho_vi))
        correlacao = anexos_rtc.extrair_correlacao_indop(Planilha(caminho_viii))
        origem_vi = self._origem(
            caminho_vi,
            "NT SE/CGNFS-e 009 — Anexo VI (Leiaute SRN), aba MUN.INCID_INFO.SERV.",
            obtido_em,
        )
        origem_viii = self._origem(
            caminho_viii,
            "NT SE/CGNFS-e 009 — Anexo VIII (correlação item × NBS × INDOP × cClassTrib)",
            obtido_em,
        )
        self._gravar("localidade_incidencia.json", origem_vi, {"regras": localidade}, saida)
        self._gravar("correlacao_indop.json", origem_viii, correlacao, saida)
        contagem = {}
        for regra in localidade.values():
            contagem[regra] = contagem.get(regra, 0) + 1
        self.stdout.write(
            f"Serviços na aba de incidência: {len(localidade)} {dict(sorted(contagem.items()))}"
        )
        pares = sum(len(por_nbs) for por_nbs in correlacao["itens"].values())
        self.stdout.write(
            f"Anexo VIII: {len(correlacao['itens'])} itens da LC 116 e {pares} pares item × NBS"
        )

    def _gravar_vii(self, caminho, obtido_em, saida):
        indicadores = anexos_rtc.extrair_local_do_fornecimento(Planilha(caminho))
        origem = self._origem(
            caminho,
            "NT SE/CGNFS-e 009 — Anexo VII (indicadores da operação), aba cIndOp Public, "
            "coluna NFSeLocIncidIBS",
            obtido_em,
        )
        self._gravar("indop_local_fornecimento.json", origem, {"indicadores": indicadores}, saida)
        contagem = {}
        for registro in indicadores.values():
            contagem[registro["classe"]] = contagem.get(registro["classe"], 0) + 1
        self.stdout.write(
            f"Anexo VII: {len(indicadores)} indicadores {dict(sorted(contagem.items()))}"
        )
