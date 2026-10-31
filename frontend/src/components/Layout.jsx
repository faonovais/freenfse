import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { buscarVersaoApi } from '../api/versao.js'
import { useAuth } from '../contexts/AuthContext.jsx'
import { useConfirmacao } from '../contexts/ConfirmacaoContext.jsx'
import { useTema } from '../contexts/TemaContext.jsx'
import { haFormularioSujo } from '../hooks/useFormularioSujo.js'
import { useLogoUrl } from '../hooks/useLogoUrl.js'
import Aviso from './Aviso.jsx'
import EmblemaAmbiente from './EmblemaAmbiente.jsx'
import SelectBusca from './SelectBusca.jsx'
import SeletorTema from './SeletorTema.jsx'

const classeLink = ({ isActive }) =>
  `block rounded px-3 py-2 text-sm hover:text-accent ${isActive ? 'text-accent' : ''}`

function VersaoDoSistema() {
  const [versaoApi, setVersaoApi] = useState(null)
  const [indisponivel, setIndisponivel] = useState(false)

  const consultar = useCallback(async () => {
    const resposta = await buscarVersaoApi()
    setIndisponivel(!resposta.ok)
    setVersaoApi(resposta.ok ? resposta.dados.versao : null)
  }, [])

  useEffect(() => {
    // Consulta inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    consultar()
  }, [consultar])

  return (
    <footer className="mt-auto border-t border-gray-200 px-4 py-3 text-xs text-gray-600 dark:border-gray-800 dark:text-gray-400">
      <span>Interface: v{__VERSAO_APP__}</span>
      {' · '}
      <span role="status">
        {indisponivel && 'API indisponível'}
        {!indisponivel && versaoApi === null && 'Consultando a API…'}
        {!indisponivel && versaoApi !== null && `API: v${versaoApi}`}
      </span>
      {indisponivel && (
        <button type="button" className="botao-leve ml-2" onClick={consultar}>
          Consultar novamente
        </button>
      )}
    </footer>
  )
}

/**
 * Estrutura das telas autenticadas. A empresa ativa é escolhida POR ABA: o nome e o
 * CNPJ ficam sempre visíveis no topo para que ninguém opere na empresa errada.
 */
export default function Layout() {
  const { usuario, empresas, empresaAtiva, identidade, trocarEmpresa, sair, temPermissao } = useAuth()
  const confirmar = useConfirmacao()
  const { escuro } = useTema()
  const tema = escuro ? 'escuro' : 'claro'
  const urlDoLogo = useLogoUrl(tema, identidade?.logo?.[tema] ?? identidade?.logo?.claro)
  const certificado = identidade?.certificado

  async function aoTrocarEmpresa(id) {
    if (haFormularioSujo()) {
      const trocar = await confirmar({
        titulo: 'Trocar de empresa?',
        mensagem: 'Há alterações não salvas nesta tela. Se trocar de empresa agora, elas serão perdidas.',
        variante: 'perigo',
        textoConfirmar: 'Trocar e descartar',
        textoCancelar: 'Continuar editando',
      })
      if (!trocar) return
    }
    trocarEmpresa(id)
  }

  const opcoesEmpresa = empresas.map((empresa) => ({
    valor: empresa.id,
    rotulo: empresa.razao_social,
    detalhe: empresa.cnpj_formatado,
  }))

  return (
    <div className="flex min-h-screen flex-col bg-gray-100 text-gray-800 dark:bg-[#121212] dark:text-gray-300">
      <header className="border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="flex flex-wrap items-center gap-4 px-4 py-3">
          <span className="font-title text-xl text-gray-900 dark:text-gray-100">freenfse</span>
          {urlDoLogo && (
            <img src={urlDoLogo} alt={`Logo de ${empresaAtiva?.razao_social ?? 'a empresa'}`} className="h-8 max-w-40 object-contain" />
          )}

          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            {empresas.length > 0 ? (
              <div className="w-72 max-w-full">
                <SelectBusca
                  rotulo="Empresa ativa"
                  opcoes={opcoesEmpresa}
                  valor={empresaAtiva?.id ?? null}
                  aoMudar={aoTrocarEmpresa}
                  vazio="Nenhuma empresa encontrada"
                />
              </div>
            ) : (
              <span className="text-sm text-gray-600 dark:text-gray-400">Nenhuma empresa liberada</span>
            )}
            {empresaAtiva && (
              <p className="text-sm" aria-label="Empresa em operação">
                <strong className="text-gray-900 dark:text-gray-100">{empresaAtiva.razao_social}</strong>
                <span className="ml-2 text-gray-600 dark:text-gray-400">{empresaAtiva.cnpj_formatado}</span>
              </p>
            )}
            <EmblemaAmbiente ambiente={identidade?.ambiente} />
          </div>

          <SeletorTema />
          <div className="flex items-center gap-3 text-sm">
            <span title={usuario.email}>{usuario.nome || usuario.email}</span>
            <button type="button" className="botao-leve" onClick={sair}>
              Sair
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 flex-col md:flex-row">
        <nav
          aria-label="Menu principal"
          className="border-b border-gray-200 p-3 md:w-56 md:border-r md:border-b-0 dark:border-gray-800"
        >
          <NavLink to="/" end className={classeLink}>
            Início
          </NavLink>
          {usuario.is_master && (
            <>
              <p className="titulo-grupo-menu mt-4 px-3">Administração</p>
              <NavLink to="/admin/empresas" className={classeLink}>
                Empresas
              </NavLink>
              <NavLink to="/admin/usuarios" className={classeLink}>
                Usuários
              </NavLink>
              <NavLink to="/admin/vinculos" className={classeLink}>
                Vínculos
              </NavLink>
            </>
          )}
          {temPermissao('nfse.consultar') && (
            <>
              <p className="titulo-grupo-menu mt-4 px-3">Notas fiscais</p>
              <NavLink to="/fiscal/notas" className={classeLink}>
                NFS-e emitidas
              </NavLink>
            </>
          )}
          {temPermissao('cadastro.consultar') && (
            <>
              <p className="titulo-grupo-menu mt-4 px-3">Cadastros</p>
              <NavLink to="/cadastros/pessoas" className={classeLink}>
                Pessoas
              </NavLink>
              <NavLink to="/cadastros/servicos" className={classeLink}>
                Serviços
              </NavLink>
            </>
          )}
          {temPermissao('config.consultar') && (
            <>
              <p className="titulo-grupo-menu mt-4 px-3">Configuração fiscal</p>
              <NavLink to="/fiscal/parametros" className={classeLink}>
                Parâmetros fiscais
              </NavLink>
              <NavLink to="/fiscal/certificado" className={classeLink}>
                Certificado A1
              </NavLink>
              <NavLink to="/fiscal/logo" className={classeLink}>
                Logo da empresa
              </NavLink>
            </>
          )}
          <p className="titulo-grupo-menu mt-4 px-3">Conta</p>
          <NavLink to="/seguranca/2fa" className={classeLink}>
            Verificação em duas etapas
          </NavLink>
        </nav>

        <main className="flex-1 p-4 md:p-8">
          {certificado?.faixa_alerta != null && (
            <Aviso tipo={certificado.vencido ? 'erro' : 'atencao'} className="mb-4">
              {certificado.vencido
                ? 'O certificado digital da empresa venceu: não é possível emitir notas até enviar um novo. '
                : `O certificado digital da empresa vence em ${certificado.dias_para_vencer} dia(s). `}
              {temPermissao('config.consultar') && (
                <Link className="underline" to="/fiscal/certificado">
                  Ver certificado
                </Link>
              )}
            </Aviso>
          )}
          {/* A chave remonta a tela ao trocar de empresa: nenhum dado da empresa anterior sobra. */}
          <Outlet key={empresaAtiva?.id ?? 'sem-empresa'} />
        </main>
      </div>

      <VersaoDoSistema />
    </div>
  )
}
