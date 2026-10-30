import '@testing-library/jest-dom/vitest'

import { vi } from 'vitest'

// O logo é exibido por URL local (blob). Nos testes a URL é fixa e previsível.
URL.createObjectURL = vi.fn(() => 'blob:logo-falso')
URL.revokeObjectURL = vi.fn()
