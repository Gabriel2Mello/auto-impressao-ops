'use strict';
// Carregado somente na demonstração; usa os mesmos controles e validações da tela.
const configuracoesDemo = $('configuracoes-demo');
window.addEventListener('keydown', evento => {
  if (evento.key === 'Escape' && configuracoesDemo.open) {
    configuracoesDemo.open = false;
    configuracoesDemo.querySelector('summary').focus();
  }
});
for (const nome of ['pointerdown', 'focusin']) window.addEventListener(nome, evento => {
  if (configuracoesDemo.open && !configuracoesDemo.contains(evento.target)) configuracoesDemo.open = false;
});
document.getElementById('demo-exemplo').onclick = () => {
  if (ocupado || pendente || encerrado) return;
  document.querySelector('[data-modo="lista"]').click();
  $('ordens').value = '123456\n123457\n123458\n123459\n123460';
  $('setor-lista').value = '10';
  invalidar();
  configuracoesDemo.open = false;
  $('ordens').focus();
};
document.getElementById('demo-resultado').onchange = async evento => {
  const controle = evento.target;
  if (ocupado || pendente || encerrado || !online) return;
  pendente = true; atualizarBotoes();
  try {
    await api('/api/demonstracao', {resultado:controle.value});
    controle.dataset.anterior = controle.value;
    $('demo-mensagem').textContent = '';
  } catch (erro) {
    controle.value = controle.dataset.anterior || 'sucesso';
    $('demo-mensagem').textContent = erro.message;
  } finally { pendente = false; atualizarBotoes(); }
};
