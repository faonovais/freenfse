import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../api/empresaAtiva.js'
import { instalarApiFalsa } from '../testes/apiFalsa.js'
import { useLogoUrl } from './useLogoUrl.js'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.unstubAllGlobals()
  URL.createObjectURL.mockClear()
  URL.revokeObjectURL.mockClear()
})

describe('useLogoUrl', () => {
  it('sem versão do logo não busca nada', () => {
    const { chamadas } = instalarApiFalsa({})

    const { result } = renderHook(() => useLogoUrl('claro', undefined))

    expect(result.current).toBeNull()
    expect(chamadas).toEqual([])
  })

  it('busca o logo do tema e devolve uma URL local', async () => {
    instalarApiFalsa({ 'GET /api/fiscal/logo/escuro/': { status: 200, blob: new Blob(['x']) } })

    const { result } = renderHook(() => useLogoUrl('escuro', 'v1'))

    await waitFor(() => expect(result.current).toBe('blob:logo-falso'))
  })

  it('busca de novo quando a versão muda e libera a URL anterior', async () => {
    const { chamadas } = instalarApiFalsa({
      'GET /api/fiscal/logo/claro/': { status: 200, blob: new Blob(['x']) },
    })
    const { result, rerender, unmount } = renderHook(({ versao }) => useLogoUrl('claro', versao), {
      initialProps: { versao: 'v1' },
    })
    await waitFor(() => expect(result.current).toBe('blob:logo-falso'))

    rerender({ versao: 'v2' })
    await waitFor(() => expect(chamadas.length).toBe(2))
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1))
    unmount()

    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  })

  it('devolve null quando o servidor não tem o logo', async () => {
    instalarApiFalsa({ 'GET /api/fiscal/logo/claro/': { status: 404, dados: null } })

    const { result } = renderHook(() => useLogoUrl('claro', 'v1'))
    await new Promise((resolver) => setTimeout(resolver, 50))

    expect(result.current).toBeNull()
  })
})
