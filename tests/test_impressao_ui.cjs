const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const caminho = require('node:path');

function painel() {
  let alteracoes = 0, leitura, recusarLeitura;
  const requisicoes = [], eventos = {}, respostasConfirmacao = [];
  class Elemento {
    constructor() { this.children = []; this.dataset = {}; this.value = ''; this.classList = {toggle() {}}; }
    set textContent(valor) { this.texto = valor; alteracoes++; }
    get textContent() { return this.texto; }
    append(...filhos) { this.children.push(...filhos); alteracoes++; }
    replaceChildren(...filhos) { this.children = filhos; alteracoes++; }
    setAttribute() {}
    addEventListener() {}
    focus() {}
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
      return {ok: true, json: async () => estado};
    }
  };
  vm.runInNewContext(fs.readFileSync(caminho.join(__dirname, '../src/impressao.js'), 'utf8'), sandbox);
  return {
    eventos, requisicoes, respostasConfirmacao, obter, estado,
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
