const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const caminho = require('node:path');

function painel() {
  let alteracoes = 0, leitura, recusarLeitura;
  const requisicoes = [], eventos = {}, respostasConfirmacao = [], respostas = new Map();
  class Elemento {
    constructor() { this.children = []; this.dataset = {}; this.value = ''; this.classList = {toggle() {}}; }
    set textContent(valor) { this.texto = valor; alteracoes++; }
    get textContent() { return this.texto; }
    append(...filhos) { this.children.push(...filhos); alteracoes++; }
    replaceChildren(...filhos) { this.children = filhos; this.value = ''; alteracoes++; }
    setAttribute() {}
    addEventListener() {}
    focus() {}
    showModal() { this.open = true; }
    close() { this.open = false; }
    querySelectorAll() { return this.children.flatMap(filho => filho.tag === 'input' ? [filho] : filho.querySelectorAll()); }
  }
  const elementos = new Map();
  const obter = id => { if (!elementos.has(id)) elementos.set(id, new Elemento()); return elementos.get(id); };
  const estado = {ocupado: false, impressora: 'Fila sintética', fase: 'pronto', mensagem: 'Pronto', atual: '', enviadas: 0, total: 0, atividade: []};
  const sandbox = {
    document: {
      getElementById: obter, querySelector: () => ({content: 'token-sintetico'}), querySelectorAll: () => [],
      documentElement: {dataset: {}}, createElement: tag => Object.assign(new Elemento(), {tag})
    },
    window: {addEventListener: (nome, funcao) => { eventos[nome] = funcao; }},
    crypto: {randomUUID: () => 'pagina-sintetica'}, AbortController, AbortSignal, TextDecoder,
    matchMedia: () => ({matches: false, addEventListener() {}}),
    localStorage: {getItem() { return null; }, setItem() {}},
    confirm: () => respostasConfirmacao.shift(),
    // Qualquer retorno ao polling em segundo plano faz os testes falharem.
    setTimeout() { throw Error('O painel parado não deve agendar atualização.'); },
    fetch: async (url, opcoes) => {
      requisicoes.push({url, opcoes});
      if (url === '/api/acompanhar') {
        opcoes.signal.addEventListener('abort', () => recusarLeitura?.(Error('Cancelado')));
        return {ok: true, body: {getReader: () => ({read: () => new Promise((resolve, reject) => { leitura = resolve; recusarLeitura = reject; })})}};
      }
      if (respostas.has(url)) return respostas.get(url);
      if (url === '/api/impressoras') return {ok: true, json: async () => ({impressoras: ['Fila sintética', 'EPSON'], impressora: estado.impressora})};
      if (url === '/api/impressora') estado.impressora = JSON.parse(opcoes.body).impressora;
      if (url === '/api/conferir') return {ok: true, json: async () => ({lotes: [{setor: '10', ordens: ['000001']}], total: 1})};
      return {ok: true, json: async () => estado};
    }
  };
  vm.runInNewContext(fs.readFileSync(caminho.join(__dirname, '../src/impressao.js'), 'utf8'), sandbox);
  return {
    eventos, requisicoes, respostasConfirmacao, respostas, obter, estado,
    alteracoes: () => alteracoes,
    enviar: mensagem => leitura({value: new TextEncoder().encode(mensagem), done: false})
  };
}
const avancar = () => new Promise(resolve => setImmediate(resolve));

test('painel parado não consulta periodicamente nem redesenha o mesmo estado', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  const anterior = ui.alteracoes();
  ui.enviar(': conexao\n\n'); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  assert.equal(ui.alteracoes(), anterior);
  assert.deepEqual(ui.requisicoes.map(item => item.url), ['/api/acompanhar']);
  ui.eventos.pagehide();
});

test('cancelar o aviso de saída preserva conexão e não envia encerramento', async () => {
  const ui = painel(); await avancar();
  let impediu = false;
  const evento = {preventDefault() { impediu = true; }};
  ui.eventos.beforeunload(evento);
  assert.equal(impediu, true);
  assert.equal(evento.returnValue, '');
  assert.equal(ui.requisicoes.length, 1);
  assert.equal(ui.requisicoes[0].opcoes.signal.aborted, false);
  // Só a saída efetiva, após a confirmação do navegador, dispara pagehide.
  ui.eventos.pagehide();
  const fechamento = ui.requisicoes.find(item => item.url === '/api/fechar-pagina');
  assert.equal(fechamento.opcoes.keepalive, true);
  assert.equal(JSON.parse(fechamento.opcoes.body).pagina, 'pagina-sintetica');
  assert.equal(ui.requisicoes[0].opcoes.signal.aborted, true);
});

test('mudanças do processamento atualizam a tela e o estado final permanece estável', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  ui.enviar(`data: ${JSON.stringify({...ui.estado, ocupado: true, fase: 'imprimindo', total: 2, atual: '000001'})}\n\n`);
  await avancar();
  assert.equal(ui.obter('campos').disabled, true);
  assert.equal(ui.obter('parar').hidden, false);
  ui.enviar(`data: ${JSON.stringify({...ui.estado, fase: 'concluido', total: 2, enviadas: 2})}\n\n`);
  await avancar();
  assert.equal(ui.obter('enviadas').textContent, 2);
  assert.equal(ui.obter('campos').disabled, false);
  assert.equal(ui.obter('parar').hidden, true);
  const anterior = ui.alteracoes();
  ui.enviar(': conexao\n\n'); await avancar();
  assert.equal(ui.alteracoes(), anterior);
  assert.equal(ui.requisicoes.length, 1);
  ui.eventos.pagehide();
});

test('Encerrar pede confirmação e dispensa um segundo aviso ao fechar a aba', async () => {
  const ui = painel(); await avancar();
  ui.respostasConfirmacao.push(false);
  await ui.obter('encerrar').onclick();
  assert.equal(ui.requisicoes.length, 1);
  ui.respostasConfirmacao.push(true);
  await ui.obter('encerrar').onclick();
  assert.equal(ui.requisicoes.at(-1).url, '/api/encerrar');
  let impediu = false;
  ui.eventos.beforeunload({preventDefault() { impediu = true; }});
  assert.equal(impediu, false);
});

test('seletor lista filas ao abrir, permite atualizar e confirma a impressora escolhida', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  await ui.obter('selecionar-impressora').onclick();
  assert.equal(ui.obter('dialogo-impressora').open, true);
  assert.deepEqual(ui.obter('lista-impressoras').children.map(item => item.textContent), ['Fila sintética', 'EPSON']);
  assert.equal(ui.obter('lista-impressoras').value, 'Fila sintética');
  ui.obter('lista-impressoras').value = 'EPSON';
  ui.obter('lista-impressoras').onchange();
  await ui.obter('atualizar-impressoras').onclick();
  assert.equal(ui.obter('lista-impressoras').value, 'EPSON');
  await ui.obter('confirmar-impressora').onclick();
  assert.equal(ui.requisicoes.at(-1).url, '/api/impressora');
  assert.equal(JSON.parse(ui.requisicoes.at(-1).opcoes.body).impressora, 'EPSON');
  assert.equal(ui.obter('dialogo-impressora').open, false);
  assert.equal(ui.obter('impressora').textContent, 'Impressora: EPSON');
  assert.equal(ui.requisicoes.some(item => item.url === '/api/iniciar'), false);
  ui.eventos.pagehide();
});

test('lista vazia e falha de consulta bloqueiam confirmação e permitem tentar novamente', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  ui.respostas.set('/api/impressoras', {ok: true, json: async () => ({impressoras: [], impressora: '', aviso_impressora: 'Nenhuma impressora instalada.'})});
  await ui.obter('selecionar-impressora').onclick();
  assert.equal(ui.obter('confirmar-impressora').disabled, true);
  assert.equal(ui.obter('aviso-lista-impressoras').textContent, 'Nenhuma impressora instalada.');
  ui.respostas.set('/api/impressoras', {ok: false, json: async () => ({erro: 'Erro sintético'})});
  await ui.obter('atualizar-impressoras').onclick();
  assert.equal(ui.obter('erro-impressora').textContent, 'Erro sintético');
  assert.equal(ui.obter('confirmar-impressora').disabled, true);
  assert.equal(ui.obter('atualizar-impressoras').disabled, false);
  ui.eventos.pagehide();
});

test('início inclui a impressora exibida e bloqueia troca durante o lote', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  await ui.obter('formulario').onsubmit({preventDefault() {}});
  await ui.obter('imprimir').onclick();
  assert.equal(ui.requisicoes.at(-1).url, '/api/iniciar');
  assert.equal(JSON.parse(ui.requisicoes.at(-1).opcoes.body).impressora, 'Fila sintética');
  ui.enviar(`data: ${JSON.stringify({...ui.estado, ocupado: true, fase: 'imprimindo'})}\n\n`); await avancar();
  assert.equal(ui.obter('selecionar-impressora').disabled, true);
  const quantidade = ui.requisicoes.length;
  await ui.obter('selecionar-impressora').onclick();
  assert.equal(ui.requisicoes.length, quantidade);
  ui.eventos.pagehide();
});

test('incerteza persistida bloqueia impressão e só libera após conferência explícita', async () => {
  const ui = painel(); await avancar();
  ui.estado.historico = [{id: 'incerto-1', numero: '000123', setor: '10', situacao: 'envio_iniciado', impressora: 'Fila sintética', atualizado_em: '2026-10-21T10:00:00+00:00'}];
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  await ui.obter('formulario').onsubmit({preventDefault() {}});
  assert.equal(ui.obter('imprimir').disabled, true);
  await ui.obter('imprimir').onclick();
  assert.equal(ui.requisicoes.some(item => item.url === '/api/iniciar'), false);
  const botao = ui.obter('recuperacao').children[0].children[1];
  ui.respostasConfirmacao.push(false); await botao.onclick();
  assert.equal(ui.requisicoes.some(item => item.url === '/api/conferir-impressao'), false);
  ui.respostasConfirmacao.push(true); await botao.onclick();
  const requisicao = ui.requisicoes.find(item => item.url === '/api/conferir-impressao');
  assert.equal(JSON.parse(requisicao.opcoes.body).conferi_fila_e_papel, true);
  assert.equal(JSON.parse(requisicao.opcoes.body).resultado, 'conferido_enviado');
  assert.equal(ui.requisicoes.some(item => item.url === '/api/iniciar'), false);
  ui.eventos.pagehide();
});
