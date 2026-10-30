// Lê só arquivos do próprio repositório (docs/design-system.md §5).
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const raizFrontend = join(import.meta.dirname, '..')
const css = readFileSync(join(raizFrontend, 'src/index.css'), 'utf-8')

function listarArquivos(pasta) {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = join(pasta, nome)
    return statSync(caminho).isDirectory() ? listarArquivos(caminho) : [caminho]
  })
}

describe('tokens do design system', () => {
  it('define a cor de destaque e as fontes', () => {
    expect(css).toContain('--color-accent: #ff5900;')
    expect(css).toContain("--font-title: 'Poppins', sans-serif;")
    expect(css).toContain("--font-body: 'Source Code Pro', monospace;")
  })

  it('define a rampa de dados e os estados semânticos', () => {
    for (let i = 1; i <= 6; i += 1) expect(css).toContain(`--color-data-${i}:`)
    for (const estado of ['sucesso', 'atencao', 'alerta', 'erro', 'neutro']) {
      expect(css).toContain(`--color-estado-${estado}:`)
    }
  })

  it('sobrescreve os tokens de gráfico no escuro sem :where()', () => {
    expect(css).toMatch(/^\.dark \{/m)
    expect(css).not.toMatch(/:where\(\.dark\)\s*\{/)
  })
})

describe('base do design system da Topo', () => {
  it('declara a origem no cabeçalho, sem apontar para repositório privado', () => {
    const cabecalho = css.split('\n').slice(0, 3).join('\n')
    expect(cabecalho).toContain('Baseado no design system da Topo')
    // Nenhum caminho "dono/repositório" nem hash de commit de repositório privado.
    expect(css).not.toMatch(/topoconsultoria\/|@[0-9a-f]{7,40}\b|origem:/i)
  })

  it.each(['botao-acao-grid', 'celula-acoes', 'titulo-grupo-menu'])('mantém @utility %s', (nome) => {
    expect(css).toMatch(new RegExp(`@utility ${nome} \\{`))
  })

  it('usa Source Code Pro 300 no claro e 400 no escuro, e Poppins 900 nos títulos', () => {
    expect(css).toMatch(/body \{\s*font-family: var\(--font-body\);\s*font-weight: 300;/)
    expect(css).toMatch(/:where\(\.dark\) body \{\s*font-weight: 400;/)
    expect(css).toMatch(/h1, h2, h3, h4, h5, h6, \.font-title \{[^}]*font-weight: 900;/)
  })
})

describe('utilitários de botão e campo', () => {
  it.each(['botao', 'botao-leve', 'botao-perigo', 'campo'])('declara @utility %s', (nome) => {
    expect(css).toMatch(new RegExp(`@utility ${nome} \\{`))
  })

  it('mantém o texto escuro no botão primário (contraste WCAG AA)', () => {
    const bloco = css.match(/@utility botao \{[^}]*\}/)[0]
    expect(bloco).toContain('text-gray-900')
    expect(bloco).not.toContain('text-white')
  })
})

describe('fontes locais', () => {
  const faces = [
    ['Poppins', 600, 'poppins-latin-600-normal.woff2'],
    ['Poppins', 900, 'poppins-latin-900-normal.woff2'],
    ['Source Code Pro', 300, 'source-code-pro-latin-300-normal.woff2'],
    ['Source Code Pro', 400, 'source-code-pro-latin-400-normal.woff2'],
    ['Source Code Pro', 600, 'source-code-pro-latin-600-normal.woff2'],
  ]

  it.each(faces)('%s %i tem @font-face e arquivo em public/fonts', (familia, peso, arquivo) => {
    expect(css).toContain(`font-family: '${familia}';`)
    expect(css).toContain(`font-weight: ${peso};`)
    expect(css).toContain(`url('/fonts/${arquivo}')`)
    expect(existsSync(join(raizFrontend, 'public/fonts', arquivo))).toBe(true)
  })

  it('inclui as licenças OFL das duas famílias', () => {
    for (const licenca of ['OFL-Poppins.txt', 'OFL-SourceCodePro.txt']) {
      const texto = readFileSync(join(raizFrontend, 'public/fonts', licenca), 'utf-8')
      expect(texto).toMatch(/SIL OPEN FONT LICENSE Version 1\.1/i)
    }
  })

  it('não carrega nada do Google Fonts', () => {
    const alvos = [join(raizFrontend, 'index.html'), ...listarArquivos(join(raizFrontend, 'src'))]
    for (const alvo of alvos.filter((a) => !a.endsWith('design-tokens.test.js'))) {
      expect(readFileSync(alvo, 'utf-8'), alvo).not.toMatch(/fonts\.(googleapis|gstatic)\.com/)
    }
  })
})
