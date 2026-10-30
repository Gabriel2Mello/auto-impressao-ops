const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const caminho = require('node:path');

function painel({temaSalvo=null, cookie='', falhaStorage=false, falhaCookie=false, desktop=false, temaBackend='escuro'}={}) {
  let alteracoes = 0, leitura, recusarLeitura;
  const requisicoes = [], eventos = {}, respostasConfirmacao = [], respostas = new Map();
  class Elemento {
    constructor() { this.children = []; this.dataset = {}; this.value = ''; this.classList = {toggle() {}}; }
    set textContent(valor) { this.texto = valor; alteracoes++; }
    get textContent() { return this.texto; }
    append(...filhos) { this.children.push(...filhos); alteracoes++; }
    replaceChildren(...filhos) { this.children = filhos; this.value = ''; alteracoes++; }
    setAttribute() {}
    addEventListener(nome,acao) { if(nome==='click'){const anterior=this.onclick;this.onclick=(...args)=>{anterior?.(...args);return acao(...args);};} }
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
      get cookie() { if (falhaCookie) throw Error('Cookies indisponíveis'); return cookie; },
      set cookie(valor) { if (falhaCookie) throw Error('Cookies indisponíveis'); cookie = valor; },
      getElementById: obter, querySelector: seletor => ({content: seletor.includes('impressao-desktop') ? (desktop ? '1' : '0') : seletor.includes('impressao-tema') ? temaBackend : 'token-sintetico'}), querySelectorAll: () => [],
      documentElement: {dataset: {},setAttribute(nome,valor){this.dataset.tema=valor;}}, createElement: tag => Object.assign(new Elemento(), {tag})
    },
    window: {addEventListener: (nome, funcao) => { eventos[nome] = funcao; }},
    crypto: {randomUUID: () => 'pagina-sintetica'}, AbortController, AbortSignal, TextDecoder,
    matchMedia: () => { throw Error('O tema não depende do sistema operacional'); },
    localStorage: {
      getItem() { if (falhaStorage) throw Error('Storage indisponível'); return temaSalvo; },
      setItem(_chave, valor) { if (falhaStorage) throw Error('Storage indisponível'); temaSalvo = valor; },
    },
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
  obter('tema').tagName='BUTTON';
  vm.runInNewContext(fs.readFileSync(caminho.join(__dirname, '../src/nunes-tema.js'), 'utf8'), sandbox);
  vm.runInNewContext(fs.readFileSync(caminho.join(__dirname, '../src/impressao.js'), 'utf8'), sandbox);
  return {
    eventos, requisicoes, respostasConfirmacao, respostas, obter, estado, sandbox,
    alteracoes: () => alteracoes,
    enviar: mensagem => leitura({value: new TextEncoder().encode(mensagem), done: false})
  };
}
const avancar = () => new Promise(resolve => setImmediate(resolve));

test('tema escuro padrão e preferências válidas são recuperados sem consultar o sistema', () => {
  for (const [salvo, esperado] of [[null, 'escuro'], ['invalido', 'escuro'], ['claro', 'claro'], ['escuro', 'escuro']]) {
    const ui = painel({temaSalvo: salvo});
    assert.equal(ui.sandbox.document.documentElement.dataset.tema, esperado);
    assert.equal(ui.obter('tema').textContent, esperado === 'escuro' ? 'Tema claro' : 'Tema escuro');
    if (salvo === esperado) assert.match(ui.sandbox.document.cookie, new RegExp(`^nunes-impressao-tema=${esperado};`));
    ui.eventos.pagehide();
  }
});

test('alternância salva a preferência e cookie restaura o tema com storage de outra porta', () => {
  const ui = painel();
  assert.equal(ui.sandbox.document.documentElement.dataset.temaAnimado, undefined);
  ui.obter('tema').onclick();
  assert.equal(ui.sandbox.document.documentElement.dataset.temaAnimado, '1');
  assert.equal(ui.sandbox.document.documentElement.dataset.tema, 'claro');
  assert.equal(ui.sandbox.localStorage.getItem('nunes-impressao-tema'), 'claro');
  assert.equal(ui.sandbox.document.cookie, 'nunes-impressao-tema=claro; Path=/; Max-Age=31536000; SameSite=Strict');
  const reaberto = painel({cookie: ui.sandbox.document.cookie});
  assert.equal(reaberto.sandbox.document.documentElement.dataset.tema, 'claro');
  const conflitante = painel({cookie: ui.sandbox.document.cookie, temaSalvo: 'escuro'});
  assert.equal(conflitante.sandbox.document.documentElement.dataset.tema, 'claro');
  const invalido = painel({cookie: 'nunes-impressao-tema=claro=invalido', temaSalvo: 'escuro'});
  assert.equal(invalido.sandbox.document.documentElement.dataset.tema, 'escuro');
  reaberto.obter('tema').onclick();
  assert.equal(reaberto.sandbox.localStorage.getItem('nunes-impressao-tema'), 'escuro');
  ui.eventos.pagehide(); reaberto.eventos.pagehide(); conflitante.eventos.pagehide(); invalido.eventos.pagehide();
});

test('armazenamentos indisponíveis mantêm tema escuro inicial e alternância funcional', () => {
  const ui = painel({falhaStorage: true, falhaCookie: true});
  assert.equal(ui.sandbox.document.documentElement.dataset.tema, 'escuro');
  ui.obter('tema').onclick();
  assert.equal(ui.sandbox.document.documentElement.dataset.tema, 'claro');
  ui.eventos.pagehide();
});

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
  assert.equal(ui.obter('progresso').value, 2);
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
  assert.equal(ui.obter('impressora').textContent, 'EPSON');
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

test('falha anterior aparece como erro e permite novo lote explícito sem conferência manual', async () => {
  const ui = painel(); await avancar();
  ui.estado.historico = [{numero:'000123',setor:'10',situacao:'envio_iniciado'}];
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  assert.equal(ui.obter('resultado-erros').textContent, 1);
  assert.equal(ui.requisicoes.some(item => item.url === '/api/iniciar'), false);
  await ui.obter('formulario').onsubmit({preventDefault(){}});
  assert.equal(ui.obter('imprimir').disabled, false);
  await ui.obter('imprimir').onclick();
  assert.equal(ui.requisicoes.filter(item => item.url === '/api/iniciar').length, 1);
  assert.equal(ui.requisicoes.some(item => item.url === '/api/conferir-impressao'), false);
  ui.eventos.pagehide();
});

test('desktop restaura tema do backend, persiste a troca e dispensa aviso de aba', async () => {
  const ui = painel({desktop:true, temaSalvo:'claro', temaBackend:'escuro'});
  assert.equal(ui.sandbox.document.documentElement.dataset.tema, 'escuro');
  ui.obter('tema').onclick(); await avancar();
  const pedido = ui.requisicoes.find(item=>item.url==='/api/tema');
  assert.equal(JSON.parse(pedido.opcoes.body).tema, 'claro');
  let avisos=0;
  ui.eventos.beforeunload({preventDefault(){avisos++;}});
  assert.equal(avisos,0);
  ui.eventos.pagehide();
});

test('falha ao salvar tema no desktop informa erro e impede Encerrar pela página', async () => {
  const ui = painel({desktop:true});
  ui.respostas.set('/api/tema',{ok:false,json:async()=>({erro:'Falha sintética ao salvar'})});
  ui.obter('tema').onclick(); await avancar();
  assert.equal(ui.obter('tema-status').textContent,'Falha sintética ao salvar');
  ui.respostasConfirmacao.push(true);
  await ui.obter('encerrar').onclick();
  assert.equal(ui.requisicoes.some(item=>item.url==='/api/encerrar'),false);
  ui.eventos.pagehide();
});


test('progresso acompanha o lote e a lista distingue conclusões, pendências e erros', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  assert.equal(ui.obter('resumo-progresso').hidden, true);
  assert.equal(ui.obter('tabela-conferencia').hidden, true);
  ui.enviar(`data: ${JSON.stringify({...ui.estado, ocupado:true, total:5, fase:'imprimindo'})}\n\n`); await avancar();
  assert.equal(ui.obter('resumo-progresso').hidden, false);
  assert.equal(ui.obter('aviso-operacao').hidden, false);
  ui.enviar(`data: ${JSON.stringify({...ui.estado, fase:'erro', historico:[{numero:'123456', setor:'10', situacao:'incerto'}]})}\n\n`); await avancar();
  assert.equal(ui.obter('resultado-erros').textContent, 1);
  assert.equal(ui.obter('resultados').children[0].children[0].textContent, 'Erro');
  ui.eventos.pagehide();
});


test('novo lote não mistura progresso anterior e o resumo enviado permanece visível', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  await ui.obter('formulario').onsubmit({preventDefault(){}});
  Object.assign(ui.estado,{ocupado:true,fase:'imprimindo',total:1,atual:'000001'});
  await ui.obter('imprimir').onclick();
  assert.equal(ui.obter('tabela-conferencia').hidden,false);
  assert.equal(ui.obter('acoes-impressao').hidden,true);
  assert.equal(ui.obter('titulo-conferencia').textContent,'Lote enviado');
  Object.assign(ui.estado,{ocupado:false,fase:'concluido',enviadas:1});
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  assert.equal(ui.obter('tabela-conferencia').hidden,false);
  assert.equal(ui.obter('fase').textContent,'Concluído');
  await ui.obter('formulario').onsubmit({preventDefault(){}});
  assert.equal(ui.obter('fase').textContent,'Conferido');
  assert.equal(ui.obter('status').textContent,'Lote pronto para imprimir.');
  assert.equal(ui.obter('resumo-progresso').hidden,true);
  assert.equal(ui.obter('ordem-atual').hidden,true);
  ui.obter('adicionar').onclick();
  assert.equal(ui.obter('fase').textContent,'Preparação');
  assert.equal(ui.obter('resumo-progresso').hidden,true);
  assert.equal(ui.obter('tabela-conferencia').hidden,true);
  ui.eventos.pagehide();
});

test('resultados preservam a leitura e contam estados sem duplicar OPs', async () => {
  const ui = painel(); await avancar();
  ui.obter('resultados').scrollTop = 120;
  ui.enviar(`data: ${JSON.stringify({...ui.estado, ocupado:true, historico:[
    {numero:'1',setor:'10',situacao:'concluido'},
    {numero:'2',setor:'10',situacao:'envio_iniciado'},
    {numero:'3',setor:'20',situacao:'pendente'}]})}\n\n`); await avancar();
  assert.equal(ui.obter('resultado-concluidas').textContent,1);
  assert.equal(ui.obter('resultado-pendentes').textContent,2);
  assert.equal(ui.obter('resultado-erros').textContent,0);
  assert.equal(ui.obter('resultados').children.length,3);
  assert.equal(ui.obter('resultados').scrollTop,120);
  assert.equal(ui.obter('resultados').children[1].children[0].textContent,'Em andamento');
  ui.eventos.pagehide();
});

test('conferir abre a aba de conferência e navegar preserva o lote até mudar a entrada', async () => {
  const ui = painel(); await avancar();
  ui.enviar(`data: ${JSON.stringify(ui.estado)}\n\n`); await avancar();
  assert.equal(ui.obter('modo-conferencia').hidden, true);
  await ui.obter('formulario').onsubmit({preventDefault(){}});
  assert.equal(ui.obter('modo-conferencia').hidden, false);
  assert.equal(ui.obter('formulario').hidden, true);
  assert.equal(ui.obter('acoes-conferir').hidden, true);
  assert.equal(ui.obter('imprimir').disabled, false);
  vm.runInNewContext('selecionarAba("intervalos")', ui.sandbox);
  assert.equal(ui.obter('formulario').hidden, false);
  vm.runInNewContext('selecionarAba("conferencia")', ui.sandbox);
  assert.equal(ui.obter('imprimir').disabled, false);
  vm.runInNewContext('selecionarAba("lista")', ui.sandbox);
  assert.equal(ui.obter('imprimir').disabled, true);
  assert.equal(ui.obter('modo-lista').hidden, false);
  ui.respostas.set('/api/conferir', {ok:false,json:async()=>({erro:'Entrada inválida'})});
  await ui.obter('formulario').onsubmit({preventDefault(){}});
  assert.equal(ui.obter('modo-conferencia').hidden, true);
  assert.equal(ui.obter('mensagem').textContent, 'Entrada inválida');
  ui.eventos.pagehide();
});

test('OP atual tem destaque único e avisos de parada continuam visíveis', async () => {
  const ui = painel(); await avancar();
  const estado = {...ui.estado, ocupado:true, atual:'000030',setor:'10',fase:'imprimindo',mensagem:'Enviando OP 000030 · setor 10'};
  ui.enviar(`data: ${JSON.stringify(estado)}\n\n`); await avancar();
  assert.equal(ui.obter('status').hidden,true);
  assert.equal(ui.obter('ordem-atual').hidden,false);
  assert.equal(ui.obter('numero-op-atual').textContent,'000030');
  assert.equal(ui.obter('setor-op-atual').textContent,'Setor 10');
  ui.enviar(`data: ${JSON.stringify({...estado,mensagem:'Parada solicitada. Aguardando a OP em andamento.'})}\n\n`); await avancar();
  assert.equal(ui.obter('status').hidden,false);
  assert.match(ui.obter('status').textContent,/Parada solicitada/);
  ui.eventos.pagehide();
});

test('contorno dos cartões só finaliza após conclusão, parada ou erro', async () => {
  const ui = painel(); await avancar();
  for (const [fase,ocupado,esperado] of [['pronto',false,'false'],['imprimindo',true,'false'],['concluido',false,'true'],['imprimindo',true,'false'],['erro',false,'true'],['interrompido',false,'true']]) {
    ui.enviar(`data: ${JSON.stringify({...ui.estado,fase,ocupado})}\n\n`); await avancar();
    assert.equal(ui.obter('resumo-resultados').dataset.finalizado,esperado);
  }
  ui.eventos.pagehide();
});
