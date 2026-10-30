# Design system do freenfse

> Identidade visual baseada no design system da Topo (D18). Este documento é a especificação **versionada** do freenfse: tokens, tipografia, tema e padrões de componentes.

## 1. Tokens

### 1.1 Cor e tipografia (`@theme` do Tailwind 4)

| Token | Valor | Uso |
|---|---|---|
| `--color-accent` | `#ff5900` | Ação primária, foco, destaque |
| `--font-title` | `'Poppins', sans-serif` | `h1–h6`, `.font-title` — peso 900, `letter-spacing: -0.025em` |
| `--font-body` | `'Source Code Pro', monospace` | Corpo — peso **300** no claro, **400** no escuro |
| `--color-data-1…6` | `#ffd0a8` `#ffab6b` `#ff8534` `#ff5900` `#cc4300` `#8f2f00` | Rampa de dados para gráficos |

Pesos: Poppins 600 e 900; Source Code Pro 300, 400 e 600.

### 1.2 Superfícies e texto (escala `gray` do Tailwind)

| Papel | Claro | Escuro |
|---|---|---|
| Fundo da página | `bg-gray-100` | `#121212` |
| Cartão, formulário, painel | `bg-white` | `bg-gray-900` |
| Borda | `border-gray-200` | `border-gray-800` |
| Texto principal | `text-gray-800` | `text-gray-300` |
| Texto secundário / rótulo | `text-gray-600` | `text-gray-400` |
| Título em cartão/modal | `text-gray-900` | `text-gray-100` |

### 1.3 Estados semânticos

| Estado | Cor | Exemplos |
|---|---|---|
| Sucesso | `#16a34a` | NFS-e autorizada |
| Atenção | `#ca8a04` | Rascunho pendente, emissão incerta |
| Alerta | `#ea580c` | Certificado perto de vencer |
| Erro | `#dc2626` | Rejeitada |
| Neutro | escala `gray` | Cancelada |

### 1.4 Gráficos

`--grafico-neutro` (`#d1d5db` / `#e5e7eb`), `--grafico-neutro-linha` (`#6b7280` / `#e5e7eb`), `--grafico-hover` (`#f3f4f6` / `#1f2937`). A sobrescrita no escuro usa `.dark { }` **sem** `:where()` (senão `:root` vence).

## 2. Tema

- Classe `.dark` no `<html>`, com `@custom-variant dark (&:where(.dark, .dark *))`.
- Modos `claro`, `escuro` e `sistema`, persistidos em `localStorage` (`freenfse-tema`); no modo sistema acompanha `prefers-color-scheme`.
- Seletor de tema com ícones SVG de traço 2px em `currentColor` (sol, lua, monitor).

## 3. Utilitários centralizados (`@utility` no `index.css`)

Botões e campos são definidos **uma única vez** (D18), nunca como constantes repetidas em cada tela:

```
botao       = rounded bg-accent px-4 py-2 text-sm font-semibold text-gray-900 hover:opacity-90 disabled:opacity-50
botao-leve  = rounded border border-gray-200 dark:border-gray-800 px-3 py-1 text-sm hover:border-accent
campo       = w-full rounded border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-300 focus:outline-none focus:border-accent
botao-perigo = variante de erro (#dc2626) com texto branco
```

Também: botão de ação de grade com largura fixa, célula de ações responsiva e título de grupo do menu (Poppins 600, 12 px, maiúsculas).

**Contraste:** texto `text-gray-900` sobre `#ff5900` = 5,6:1 (WCAG AA). Não usar texto branco no botão primário (3,1:1).

## 4. Fontes

Auto-hospedadas em `frontend/public/fonts/` (`woff2`, licença OFL) com `@font-face` no `index.css`. Nada é carregado do Google Fonts: funciona sem internet externa e não envia o IP do usuário a terceiros.

## 5. Componentes base do frontend

Genéricos, sem regra de negócio: contexto de tema e seletor; modal de confirmação (variante "perigo" e confirmação por texto digitado, `role="dialog" aria-modal="true"`) com `confirmar()` baseado em Promise; proteção de formulário alterado; select com busca e multisseleção; cabeçalho de coluna e grade com ordenação local; painel recolhível; botão de ajuda contextual; cartão de indicador; cliente HTTP `{ ok, status, dados }` com CSRF e cabeçalho `X-Empresa`; mensagens de erro em linguagem simples; layout com alterador de empresa (por aba).

Regras: sem biblioteca de componentes externa; JavaScript (sem TypeScript); tokens só no `index.css`; testes de tokens leem apenas arquivos deste repositório.

## 6. Logo (D18)

O freenfse tem logo padrão próprio, e cada empresa pode enviar o **seu logo nos parâmetros da empresa**:
- versões para tema claro e escuro (a escura é opcional; sem ela, usa a clara);
- PNG ou SVG com limite de tamanho; SVG sanitizado no upload (remove scripts) ou convertido para PNG;
- exibido no cabeçalho quando a empresa está ativa e nos e-mails enviados em nome dela;
- no DANFSe, só se o layout oficial (NT 008) permitir — verificar antes de implementar;
- guardado no schema da empresa (ou volume de mídia por empresa), nunca em pasta compartilhada.
