// Os testes rodam sempre em UTC, que NÃO é o fuso de Brasília: assim qualquer tela que dependa do fuso do
// navegador (em vez de fixar America/Sao_Paulo) falha no CI, e não só em máquinas de outro país (issue #24).
export default function setup() {
  process.env.TZ = 'UTC'
}
