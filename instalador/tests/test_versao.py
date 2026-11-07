"""Versão mínima do Python do instalador (issue #30).

O instalador roda com o Python do servidor, que numa VPS comum é o da distribuição. O CI roda
esta suíte em 3.10, 3.12 e 3.14; aqui ficam a regra da versão mínima e a prova de que `instalar.py`
avisa em linguagem simples, ANTES de importar o resto, quando o Python é antigo.
"""

import subprocess
import sys

import pytest
from conftest import RAIZ
from freenfse_instalador import versao

INSTALAR = RAIZ / "instalador" / "instalar.py"

# Roda `instalar.py` como se fosse um Python 3.9. Imprime o código de saída e se algum módulo do
# instalador (além do de versão) chegou a ser importado: não pode, ou um módulo com sintaxe nova
# morreria com SyntaxError antes de a mensagem aparecer.
SCRIPT_DE_PYTHON_ANTIGO = """
import runpy, sys
caminho = sys.argv[1]
sys.argv = [caminho, "compose", "--simular"]
sys.version_info = (3, 9, 18, "final", 0)
try:
    runpy.run_path(caminho, run_name="__main__")
    codigo = 0
except SystemExit as saida:
    codigo = saida.code
importados = sorted(
    nome for nome in sys.modules
    if nome.startswith("freenfse_instalador.") and nome != "freenfse_instalador.versao"
)
print("CODIGO=%s" % codigo)
print("IMPORTADOS=%s" % importados)
"""


def test_o_minimo_declarado_e_o_3_10():
    assert versao.PYTHON_MINIMO == (3, 10)


@pytest.mark.parametrize(
    ("atual", "esperado"),
    [
        ((3, 8, 10), False),
        ((3, 9, 18), False),
        ((3, 9, 99, "final", 0), False),
        ((3, 10, 0), True),
        ((3, 10, 20, "final", 0), True),
        ((3, 12, 3), True),
        ((3, 14, 6), True),
        ((4, 0, 0), True),
    ],
)
def test_python_suficiente_pela_versao_maior_e_menor(atual, esperado):
    assert versao.python_suficiente(atual) is esperado


def test_o_python_que_roda_os_testes_atende_ao_minimo():
    assert versao.python_suficiente()


def test_mensagem_diz_o_minimo_a_versao_em_uso_e_o_que_fazer():
    mensagem = versao.mensagem_de_python_antigo((3, 9, 18, "final", 0))

    assert "Python 3.10 ou mais novo" in mensagem
    assert "este é o Python 3.9.18" in mensagem
    assert "python3.12" in mensagem  # o que fazer: rodar com um Python mais novo


def test_como_texto():
    assert versao.como_texto((3, 10, 4, "final", 0)) == "3.10"
    assert versao.como_texto((3, 10, 4, "final", 0), partes=3) == "3.10.4"


def test_python_antigo_recebe_mensagem_clara_e_nada_alem_do_modulo_de_versao_e_importado():
    resultado = subprocess.run(
        [sys.executable, "-B", "-c", SCRIPT_DE_PYTHON_ANTIGO, str(INSTALAR)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert "CODIGO=2" in resultado.stdout, resultado.stderr
    assert "IMPORTADOS=[]" in resultado.stdout
    assert "Python 3.10 ou mais novo" in resultado.stderr
    assert "este é o Python 3.9.18" in resultado.stderr
    assert "SyntaxError" not in resultado.stderr
    assert "SIMULAÇÃO" not in resultado.stdout  # a instalação nem começou


def test_python_atual_nao_e_barrado_pelo_guarda():
    resultado = subprocess.run(
        [sys.executable, "-B", str(INSTALAR), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert resultado.returncode == 0, resultado.stderr
    assert "compose" in resultado.stdout
