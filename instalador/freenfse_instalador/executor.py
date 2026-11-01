"""Execução de comandos: de verdade ou simulada (só registra), sem segredo na linha de comando.

Os segredos passam por variáveis de ambiente (`env=`) ou pela entrada padrão (`entrada=`), nunca
como argumento: a lista de processos do servidor (`ps`) é visível a outros usuários.
"""

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Resultado:
    """Resultado de um comando."""

    codigo: int = 0
    saida: str = ""
    erro: str = ""


class ErroDeComando(Exception):
    """Um comando necessário falhou."""

    def __init__(self, comando, resultado):
        """Guarda o comando e a saída de erro (já sem segredo: nunca ecoamos o ambiente)."""
        self.comando = comando
        self.resultado = resultado
        super().__init__(
            f"Falhou ({resultado.codigo}): {' '.join(comando)}\n{resultado.erro.strip()[-800:]}"
        )


class Executor:
    """Executa de verdade, no servidor."""

    simulado = False

    def executar(
        self,
        comando,
        *,
        verificar=True,
        entrada=None,
        env=None,
        cwd=None,
        usuario=None,
        transmitir=None,
    ):
        """Roda `comando` (lista); com `verificar`, levanta `ErroDeComando` se falhar.

        Com `transmitir` (uma função), cada linha de saída é entregue a ela assim que sai — para
        comandos longos (build, pip, certbot) o usuário vê o andamento em vez de uma tela parada.
        """
        if transmitir is not None:
            resultado = self._transmitindo(comando, entrada, env, cwd, usuario, transmitir)
        else:
            processo = subprocess.run(  # noqa: S603
                comando,
                input=entrada,
                capture_output=True,
                text=True,
                env=env,
                cwd=cwd,
                user=usuario,
            )
            resultado = Resultado(processo.returncode, processo.stdout, processo.stderr)
        if verificar and resultado.codigo != 0:
            raise ErroDeComando(comando, resultado)
        return resultado

    @staticmethod
    def _transmitindo(comando, entrada, env, cwd, usuario, transmitir):
        processo = subprocess.Popen(  # noqa: S603
            comando,
            stdin=subprocess.PIPE if entrada is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=cwd,
            user=usuario,
        )
        if entrada is not None:
            processo.stdin.write(entrada)
            processo.stdin.close()
        linhas = []
        for linha in processo.stdout:
            linha = linha.rstrip("\n")
            linhas.append(linha)
            transmitir(f"    {linha}")
        processo.wait()
        saida = "\n".join(linhas)
        return Resultado(processo.returncode, saida, saida)

    def existe(self, programa):
        """Se o programa está no PATH."""
        return shutil.which(programa) is not None


class ExecutorSimulado:
    """Não executa nada: registra o que seria feito e devolve respostas combinadas."""

    simulado = True

    def __init__(self, respostas=None, programas=None):
        """`respostas`: prefixo do comando (tupla) -> `Resultado`; `programas`: os que 'existem'."""
        self.comandos = []
        self.entradas = []
        self.ambientes = []
        self._respostas = respostas or {}
        self._programas = programas

    def executar(
        self,
        comando,
        *,
        verificar=True,
        entrada=None,
        env=None,
        cwd=None,
        usuario=None,
        transmitir=None,
    ):
        """Registra o comando (com a entrada e o ambiente separados) e devolve o resultado."""
        self.comandos.append(list(comando))
        self.entradas.append(entrada)
        self.ambientes.append(env)
        for prefixo, resultado in self._respostas.items():
            if tuple(comando[: len(prefixo)]) == prefixo:
                if verificar and resultado.codigo != 0:
                    raise ErroDeComando(comando, resultado)
                return resultado
        return Resultado()

    def existe(self, programa):
        """Diz se o programa existe: sempre, ou só os informados no construtor."""
        return True if self._programas is None else programa in self._programas
