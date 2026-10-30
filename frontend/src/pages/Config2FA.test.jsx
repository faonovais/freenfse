import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { limparEmpresaAtiva } from '../api/empresaAtiva.js'
import { respostaEu } from '../testes/apiFalsa.js'
import { BASE, montarApp, rotasAutenticado } from '../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
})

const TOTP = `${BASE}/account/authenticators/totp`

describe('configuração do 2FA', () => {
  it('informa quando o 2FA já está ativo', async () => {
    montarApp({ rota: '/seguranca/2fa', rotasApi: rotasAutenticado() })

    expect(await screen.findByText('ativa', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Configurar' })).not.toBeInTheDocument()
  })

  it('configura: confirma a senha, mostra QR e chave, valida o código e exibe os códigos de recuperação', async () => {
    let ativo = false
    const eu = () => respostaEu({ mfa: { ativo, obrigatorio: true } })
    const { chamadas } = montarApp({
      rota: '/seguranca/2fa',
      rotasApi: rotasAutenticado({
        extras: {
          'GET /api/eu/': () => eu(),
          [`POST ${BASE}/auth/reauthenticate`]: (chamada) =>
            chamada.corpo.password === 'senha-de-teste-123'
              ? { status: 200, dados: {} }
              : { status: 400, dados: { errors: [{ code: 'incorrect_password', message: 'Senha incorreta.' }] } },
          [`GET ${TOTP}`]: {
            status: 404,
            dados: { meta: { secret: 'JBSWY3DPEHPK3PXP', totp_url: 'otpauth://totp/freenfse:ana?secret=JBSWY3DPEHPK3PXP' } },
          },
          [`POST ${TOTP}`]: (chamada) => {
            if (chamada.corpo.code !== '654321') return { status: 400, dados: { errors: [{ code: 'incorrect_code', message: 'x' }] } }
            ativo = true
            return { status: 200, dados: {} }
          },
          [`GET ${BASE}/account/authenticators/recovery-codes`]: {
            status: 200,
            dados: { data: { unused_codes: ['aaaa-1111', 'bbbb-2222'] } },
          },
        },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Configurar' }))

    fireEvent.change(screen.getByLabelText(/Confirme a sua senha/), { target: { value: 'errada' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Confirme a sua senha/), { target: { value: 'senha-de-teste-123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument()
    expect(screen.getByTitle('QR code do autenticador')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/código de 6 dígitos/), { target: { value: '111111' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ativar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Código incorreto')

    fireEvent.change(screen.getByLabelText(/código de 6 dígitos/), { target: { value: '654321' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ativar' }))

    const codigos = await screen.findByRole('list', { name: 'Códigos de recuperação' })
    expect(codigos).toHaveTextContent('aaaa-1111')
    expect(codigos).toHaveTextContent('bbbb-2222')
    expect(screen.queryByText('JBSWY3DPEHPK3PXP')).not.toBeInTheDocument()
    await waitFor(() => expect(chamadas.filter((chamada) => chamada.caminho === '/api/eu/').length).toBeGreaterThan(1))
  })
})
