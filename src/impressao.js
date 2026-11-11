'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="impressao-token"]').content;
const desktop = document.querySelector('meta[name="impressao-desktop"]')?.content === '1';
let salvamentoTema = Promise.resolve(true);
let salvamentoConsulta = Promise.resolve(true);
function aguardarPreferencias() {
  return Promise.all([salvamentoTema, salvamentoConsulta]).then(resultados => resultados.every(Boolean));
}
let modo = 'intervalos', conferido = null, ocupado = false, online = false, encerrado = false, pendente = false, impressora = '';
let numeroIntervalo = 0, abaAtual = 'intervalos';
let estadoAtual = null, preparando = true, resumoConferencia = null;
let gruposConferencia = [];
const pagina = crypto.randomUUID();
const presenca = new AbortController();
let ultimoEstado = '', saindo = false, historico = [];
let seguirResultados = true, topoResultados = 0, resultadoAtual = null;

function atualizarSetaResultados() {
  const lista = $('resultados'), ultimo = lista.lastElementChild;
  let ultimoVisivel = false;
  if (historico.length && ultimo) {
    const area = lista.getBoundingClientRect(), item = ultimo.getBoundingClientRect();
    ultimoVisivel = item.top >= Math.max(0, area.top) - 1
      && item.bottom <= Math.min(window.innerHeight, area.bottom) + 1;
  }
  $('acompanhar-atual').hidden = seguirResultados || !resultadoAtual || ultimoVisivel;
}
function acompanharResultadoAtual() {
  atualizarSetaResultados();
  if (!seguirResultados || !resultadoAtual) return;
  const lista = $('resultados'), area = lista.getBoundingClientRect(), item = resultadoAtual.getBoundingClientRect();
  if (item.top < area.top) lista.scrollTop += item.top - area.top;
  else if (item.bottom > area.bottom) lista.scrollTop += item.bottom - area.bottom;
  topoResultados = lista.scrollTop;
  atualizarSetaResultados();
}
$('resultados').addEventListener('scroll', () => {
  if (Math.abs($('resultados').scrollTop - topoResultados) > 1) seguirResultados = false;
  atualizarSetaResultados();
});
window.addEventListener('resize', atualizarSetaResultados);
window.addEventListener('scroll', atualizarSetaResultados, true);
if (window.ResizeObserver) new window.ResizeObserver(atualizarSetaResultados).observe($('resultados'));
$('acompanhar-atual').onclick = () => { seguirResultados = true; acompanharResultadoAtual(); };

function atualizarBotoes() {
  for (const id of ['demo-resultado', 'demo-exemplo']) {
    const controle = $(id);
    if (controle) controle.disabled = ocupado || pendente || encerrado || !online;
  }
  $('tabela-conferencia').hidden = !resumoConferencia;
  $('cabecalho-conferencia').hidden = !resumoConferencia;
  $('conferencia-vazia').hidden = Boolean(resumoConferencia);
  $('requisito-impressao').hidden = !conferido;
  $('acoes-impressao').hidden = !conferido;
  $('conferir').classList.toggle('botao-principal', !conferido);
  mostrarAbas();
  mostrarAndamento();
  $('campos').disabled = ocupado || pendente || encerrado;
  $('conferir').disabled = ocupado || pendente || !online || encerrado;
  $('consultar-sisplan').disabled = ocupado || pendente || !online || encerrado;
  const automatico = Boolean($('consultar-sisplan').checked);
  $('setor-lista').disabled = automatico;
  for (const input of $('intervalos').querySelectorAll('input')) {
    if (input.dataset.campo === 'setor') input.disabled = automatico;
  }
  let selecionadas = 0;
  for (const grupo of gruposConferencia) {
    grupo.checkbox.disabled = !conferido || ocupado || pendente || !online || encerrado;
    if (grupo.checkbox.checked) selecionadas += grupo.ordens.length;
  }
  $('imprimir').disabled = !conferido || !selecionadas || ocupado || pendente || !online || !impressora || encerrado;
  $('imprimir').textContent = selecionadas ? `Imprimir ${selecionadas} ${selecionadas === 1 ? 'OP' : 'OPs'}` : 'Imprimir lote';
  if (resumoConferencia) $('resumo').textContent = `${selecionadas} de ${resumoConferencia.total} OPs selecionadas`;
  $('parar').hidden = !ocupado;
  $('selecionar-impressora').disabled = ocupado || pendente || !online || encerrado;
  $('atualizar-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('lista-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('confirmar-impressora').disabled = ocupado || pendente || !online || encerrado || !$('lista-impressoras').value;
  document.querySelectorAll('[data-aba]').forEach(botao => { botao.disabled = ocupado || pendente || encerrado; });
}
function mostrarAbas() {
  const acoes = $('acoes-conferir');
  const destino = $(modo === 'lista' ? 'rodape-lista' : 'rodape-intervalos');
  if (acoes.parentElement !== destino) destino.append(acoes);
  document.querySelectorAll('[data-aba]').forEach(botao => botao.setAttribute('aria-pressed', String(botao.dataset.aba === abaAtual)));
  $('formulario').hidden = abaAtual === 'conferencia';
  $('acoes-conferir').hidden = abaAtual === 'conferencia';
  $('modo-intervalos').hidden = abaAtual !== 'intervalos';
  $('modo-lista').hidden = abaAtual !== 'lista';
  $('modo-conferencia').hidden = abaAtual !== 'conferencia';
}
function selecionarAba(aba) {
  if (aba !== 'conferencia' && aba !== modo) {
    modo = aba;
    invalidar();
  }
  abaAtual = aba;
  mostrarAbas();
  document.querySelector('.rolagem-preparacao').scrollTop = 0;
}
function atualizarContagemOrdens() {
  const numeros = $('ordens').value.split(/[\s,;]+/)
    .filter(numero => /^[0-9]+$/.test(numero))
    .map(numero => numero.replace(/^0+/, '').padStart(6, '0'));
  const texto = 'Contagem: ' + new Set(numeros).size;
  if ($('contagem-ordens').textContent !== texto) $('contagem-ordens').textContent = texto;
}
function invalidar() {
  atualizarContagemOrdens();
  conferido = null;
  preparando = true; resumoConferencia = null;
  gruposConferencia = [];
  $('titulo-conferencia').textContent = 'Conferência';
  $('resumo').textContent = 'Informe as OPs e confira o lote.';
  $('lotes').replaceChildren();
  $('mensagem').textContent = '';
  atualizarBotoes();
}
function adicionarIntervalo() {
  if ($('intervalos').children.length >= 100) return;
  const linha = document.createElement('div'); linha.className = 'intervalo';
  const numero = ++numeroIntervalo;
  for (const [chave, titulo, valor] of [['de', 'De', ''], ['para', 'Até', ''], ['setor', 'Setor', '10']]) {
    const grupo = document.createElement('div'), label = document.createElement('label'), input = document.createElement('input');
    input.id = `${chave}-${numero}`; input.dataset.campo = chave; input.inputMode = 'numeric';
    input.maxLength = chave === 'setor' ? 6 : 12; input.autocomplete = 'off'; input.value = valor;
    input.placeholder = chave === 'de' ? 'Ex.: 123456' : chave === 'para' ? 'Mesma OP' : '10';
    label.htmlFor = input.id; label.textContent = titulo; grupo.append(label, input); linha.append(grupo);
  }
  const remover = document.createElement('button'); remover.type = 'button'; remover.textContent = '×'; remover.title = 'Remover intervalo';
  remover.setAttribute('aria-label', `Remover intervalo ${numero}`);
  remover.onclick = () => { linha.remove(); if (!$('intervalos').children.length) adicionarIntervalo(); invalidar(); };
  linha.append(remover); $('intervalos').append(linha); invalidar();
}
function entrada() {
  const consultar_sisplan = Boolean($('consultar-sisplan').checked);
  if (modo === 'lista') return {modo, consultar_sisplan, ordens: $('ordens').value, setor: $('setor-lista').value};
  return {modo, consultar_sisplan, intervalos: Array.from($('intervalos').children, linha => Object.fromEntries(
    Array.from(linha.querySelectorAll('input'), input => [input.dataset.campo, input.value])))};
}
function mostrarLotes(lotes, comFaccao) {
  $('coluna-faccao').hidden = !comFaccao;
  $('tabela-conferencia').classList.toggle('com-faccao', comFaccao);
  $('lotes').replaceChildren();
  const grupos = new Map();
  for (const [indice, lote] of lotes.entries()) {
    const chave = `${lote.faccao ?? ''}/${lote.setor}`;
    if (!grupos.has(chave)) grupos.set(chave, {lote, ordens: [], indices: []});
    const grupo = grupos.get(chave);
    grupo.ordens.push(...lote.ordens);
    grupo.indices.push(indice);
  }
  gruposConferencia = [...grupos.values()];
  if (comFaccao) gruposConferencia.sort((a, b) =>
    a.lote.faccao.localeCompare(b.lote.faccao) || a.lote.setor.localeCompare(b.lote.setor));

  const local = (codigo, nome) => codigo + (nome ? ` · ${nome}` : '');
  for (const grupo of gruposConferencia) {
    const {lote, ordens} = grupo;
    const linha = document.createElement('tr'), selecao = document.createElement('td');
    const setor = local(lote.setor, lote.setor_nome);
    const faccao = comFaccao ? local(lote.faccao, lote.faccao_nome) : '';
    const nomeSetor = (lote.setor_nome || '').normalize('NFD').replace(/\p{Diacritic}/gu, '');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = (!comFaccao || lote.faccao === '00261') && !/\bexpedicao\b/i.test(nomeSetor);
    checkbox.setAttribute('aria-label', `Imprimir setor ${setor}${faccao ? `, facção ${faccao}` : ''}`);
    checkbox.onchange = atualizarBotoes;
    grupo.checkbox = checkbox;
    selecao.append(checkbox);
    linha.append(selecao);
    const valores = [setor, ordens.length, ordens.slice(0, 100).join(' · ') + (ordens.length > 100 ? ` · … e mais ${ordens.length - 100} OPs` : '')];
    if (comFaccao) valores.unshift(faccao);
    for (const valor of valores) {
      const celula = document.createElement('td');
      celula.textContent = valor;
      linha.append(celula);
    }
    $('lotes').append(linha);
  }
}
async function api(caminho, dados) {
  const resposta = await fetch(caminho, {
    method: dados === undefined ? 'GET' : 'POST',
    keepalive: caminho === '/api/preferencia-consulta',
    headers: {Authorization: `Bearer ${token}`, ...(dados === undefined ? {} : {'Content-Type': 'application/json'})},
    body: dados === undefined ? undefined : JSON.stringify(dados), signal: AbortSignal.timeout(
      dados?.consultar_sisplan ? 30000 : 10000)
  });
  const retorno = await resposta.json();
  if (!resposta.ok) throw Error(retorno.erro || 'Não foi possível concluir a solicitação.');
  return retorno;
}
function mostrarEstado(estado) {
  const assinatura = JSON.stringify(estado);
  if (assinatura === ultimoEstado) return;
  ultimoEstado = assinatura;
  if (estado.ocupado && !ocupado) seguirResultados = true;
  estadoAtual = estado;
  if (estado.ocupado) preparando = false;
  ocupado = estado.ocupado; impressora = estado.impressora;
  historico = estado.historico || [];
  mostrarResultados();
  $('impressora').textContent = impressora || 'Nenhuma impressora selecionada.';
  $('aviso-impressora').textContent = estado.aviso_impressora || '';
  atualizarBotoes();
  acompanharResultadoAtual();
}
function mostrarAndamento() {
  if (!estadoAtual) return;
  const estado = estadoAtual;
  const novoLote = preparando && !ocupado;
  const fases = {pronto:'Pronto', imprimindo:'Em andamento', concluido:'Concluído', interrompido:'Interrompido', erro:'Erro'};
  $('fase').textContent = novoLote ? (conferido ? 'Conferido' : 'Preparação') : (fases[estado.fase] || estado.fase);
  $('fase').classList.toggle('erro', !novoLote && estado.fase === 'erro');
  $('status').textContent = novoLote ? (conferido ? 'Lote pronto para imprimir.' : 'Aguardando conferência.') : estado.mensagem;
  $('status').hidden = !novoLote && ocupado && Boolean(estado.atual) && estado.mensagem === `Enviando OP ${estado.atual} · setor ${estado.setor}`;
  $('resumo-progresso').hidden = novoLote || !estado.total;
  $('ordem-atual').hidden = novoLote || !ocupado || !estado.atual || !$('status').hidden;
  $('rotulo-op-atual').textContent = ocupado ? 'Imprimindo OP' : 'Última OP processada';
  $('numero-op-atual').textContent = estado.atual || '';
  $('setor-op-atual').textContent = estado.atual ? `Setor ${estado.setor}` : '';
  $('progresso').max = novoLote ? 1 : (estado.total || 1);
  $('progresso').value = novoLote ? 0 : estado.enviadas;
  $('aviso-operacao').hidden = !ocupado;
}
function mostrarResultados() {
  $('resumo-resultados').dataset.finalizado = String(!ocupado && ['concluido', 'interrompido', 'erro'].includes(estadoAtual.fase));
  const lista = $('resultados'), topo = lista.scrollTop;
  const contagem = {concluidas:0, pendentes:0, erros:0};
  resultadoAtual = null;
  lista.replaceChildren();
  for (const [indice, registro] of historico.entries()) {
    const concluida = ['concluido', 'conferido_enviado'].includes(registro.situacao);
    const executando = ocupado && registro.situacao === 'envio_iniciado';
    const erro = !executando && ['envio_iniciado', 'incerto'].includes(registro.situacao);
    const tipo = concluida ? 'concluidas' : erro ? 'erros' : 'pendentes';
    contagem[tipo]++;
    const linha = document.createElement('article'); linha.className = 'resultado';
    const etiqueta = document.createElement('span'); etiqueta.className = `situacao ${tipo}`;
    etiqueta.textContent = concluida ? 'Concluída' : erro ? 'Erro' : executando ? 'Em andamento' : 'Pendente';
    const posicao = document.createElement('span'); posicao.className = 'posicao-resultado';
    posicao.textContent = `${indice + 1}/${historico.length}`;
    posicao.setAttribute('aria-label', `Operação ${indice + 1} de ${historico.length}`);
    const descricao = document.createElement('p');
    const numero = document.createElement('strong'); numero.textContent = registro.numero;
    const detalhe = document.createElement('span');
    detalhe.textContent = ` · setor ${registro.setor}${erro ? ' · O processamento não foi concluído.' : ''}`;
    descricao.append(numero, detalhe); linha.append(etiqueta, descricao, posicao); lista.append(linha);
    if (concluida || erro || executando) resultadoAtual = linha;
  }
  if (!historico.length) {
    const vazio = document.createElement('p'); vazio.className = 'dica'; vazio.textContent = 'Nenhuma execução iniciada.'; lista.append(vazio);
  }
  for (const [tipo, quantidade] of Object.entries(contagem)) $(`resultado-${tipo}`).textContent = quantidade;
  lista.scrollTop = topo;
  topoResultados = lista.scrollTop;
}
async function carregarImpressoras() {
  if (pendente || ocupado || encerrado || !online) return;
  const anterior = $('lista-impressoras').value;
  pendente = true; atualizarBotoes();
  $('erro-impressora').textContent = '';
  $('aviso-lista-impressoras').textContent = 'Consultando as impressoras do Windows…';
  $('lista-impressoras').replaceChildren();
  try {
    const resultado = await api('/api/impressoras');
    for (const nome of resultado.impressoras) {
      const opcao = document.createElement('option');
      opcao.value = nome; opcao.textContent = nome; opcao.title = nome;
      $('lista-impressoras').append(opcao);
    }
    $('lista-impressoras').value = resultado.impressoras.includes(anterior) ? anterior : resultado.impressora || '';
    $('aviso-lista-impressoras').textContent = resultado.aviso_impressora || 'As filas virtuais podem solicitar um local para salvar o arquivo.';
  } catch (erro) {
    $('erro-impressora').textContent = erro.message;
    $('aviso-lista-impressoras').textContent = 'Use Atualizar lista para tentar novamente.';
  } finally { pendente = false; atualizarBotoes(); }
}
$('selecionar-impressora').onclick = async () => {
  if (ocupado || pendente || encerrado || !online) return;
  $('lista-impressoras').replaceChildren();
  $('dialogo-impressora').showModal();
  await carregarImpressoras();
};
$('atualizar-impressoras').onclick = carregarImpressoras;
$('cancelar-impressora').onclick = () => $('dialogo-impressora').close();
$('lista-impressoras').onchange = atualizarBotoes;
$('confirmar-impressora').onclick = async () => {
  if (ocupado || pendente || encerrado || !online || !$('lista-impressoras').value) return;
  pendente = true; atualizarBotoes(); $('erro-impressora').textContent = '';
  try {
    mostrarEstado(await api('/api/impressora', {impressora: $('lista-impressoras').value}));
    $('dialogo-impressora').close();
  } catch (erro) { $('erro-impressora').textContent = erro.message; }
  finally { pendente = false; atualizarBotoes(); }
};
async function acompanhar() {
  if (encerrado || saindo) return;
  try {
    const resposta = await fetch('/api/acompanhar', {
      headers: {Authorization: `Bearer ${token}`, 'X-Impressao-Pagina': pagina}, signal: presenca.signal
    });
    if (!resposta.ok || !resposta.body) throw Error('Não foi possível acompanhar o painel.');
    online = true;
    $('conexao').textContent = '';
    const leitor = resposta.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    while (!encerrado && !saindo) {
      const {value, done} = await leitor.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let fim;
      while ((fim = buffer.indexOf('\n\n')) !== -1) {
        const evento = buffer.slice(0, fim); buffer = buffer.slice(fim + 2);
        if (evento.startsWith('data: ')) mostrarEstado(JSON.parse(evento.slice(6)));
      }
    }
    if (!encerrado && !saindo) throw Error('A conexão com o programa foi encerrada.');
  } catch {
    if (encerrado || saindo) return;
    online = false; atualizarBotoes();
    $('conexao').textContent = 'Conexão perdida. Reabra o programa para continuar.';
  }
}
$('formulario').onsubmit = async evento => {
  evento.preventDefault(); if (pendente || ocupado || encerrado) return;
  pendente = true; atualizarBotoes(); $('mensagem').textContent = '';
  if ($('consultar-sisplan').checked) $('mensagem').textContent = 'Consultando facção e setor no Sisplan…';
  try {
    if (!await salvamentoConsulta) throw Error('Não foi possível salvar a opção Consultar no Sisplan. Selecione a opção novamente para tentar salvar.');
    const dados = entrada(), resultado = await api('/api/conferir', dados);
    conferido = {...dados, conferencia_id: resultado.conferencia_id}; preparando = true; resumoConferencia = resultado;
    $('mensagem').textContent = '';
    $('titulo-conferencia').textContent = 'Conferência';
    mostrarLotes(resultado.lotes, dados.consultar_sisplan);

    selecionarAba('conferencia');
    atualizarBotoes();
    $('titulo-conferencia').focus();
  } catch (erro) { conferido = null; resumoConferencia = null; $('mensagem').textContent = erro.message; }
  finally { pendente = false; atualizarBotoes(); }
};
$('imprimir').onclick = async () => {
  if (!conferido || pendente || ocupado || encerrado) return;
  const grupos_selecionados = gruposConferencia.filter(grupo => grupo.checkbox.checked).flatMap(grupo => grupo.indices);
  if (!grupos_selecionados.length) return;
  pendente = true; atualizarBotoes(); $('mensagem').textContent = '';
  try { const estado = await api('/api/iniciar', {...conferido, grupos_selecionados, impressora}); conferido = null; preparando = false; $('titulo-conferencia').textContent = 'Lote enviado'; mostrarEstado(estado); }
  catch (erro) { conferido = null; $('mensagem').textContent = erro.message + ' Confira o andamento antes de preparar outro lote.'; }
  finally { pendente = false; atualizarBotoes(); }
};
$('parar').onclick = async () => {
  try { mostrarEstado(await api('/api/parar', {})); } catch (erro) { $('mensagem').textContent = erro.message; }
};
$('encerrar').onclick = async () => {
  if (encerrado) return;
  if (!confirm('Deseja realmente encerrar o programa? A OP em andamento será concluída antes de parar.')) return;
  try {
    if (!await aguardarPreferencias()) return;
    await api('/api/encerrar', {}); encerrado = true; online = false; atualizarBotoes();
    presenca.abort();
    $('encerrar').disabled = true; $('parar').hidden = true;
    $('status').hidden = false;
    $('status').textContent = desktop ? 'Encerrando após a OP atual. Aguarde a janela fechar.' : ocupado ? 'Encerrando após a OP em andamento. Você pode fechar esta aba.' : 'Programa encerrado. Você pode fechar esta aba.';
    $('conexao').textContent = 'Painel encerrado';
  } catch (erro) { $('mensagem').textContent = erro.message; }
};
window.addEventListener('beforeunload', evento => {
  if (encerrado || desktop) return;
  evento.preventDefault();
  evento.returnValue = '';
});
window.addEventListener('pagehide', () => {
  saindo = true;
  if (!encerrado) {
    // O evento só ocorre após confirmar a saída; cancelar mantém a conexão e o programa.
    fetch('/api/fechar-pagina', {
      method: 'POST', keepalive: true,
      headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
      body: JSON.stringify({pagina})
    }).catch(() => { /* A desconexão do canal também informa o fechamento ao servidor. */ });
  }
  presenca.abort();
});
document.querySelectorAll('[data-aba]').forEach(botao => { botao.onclick = () => selecionarAba(botao.dataset.aba); });
$('campos').addEventListener('input', invalidar);
$('consultar-sisplan').onchange = () => {
  const valor = $('consultar-sisplan').checked;
  invalidar();
  salvamentoConsulta = salvamentoConsulta.then(async () => {
    try {
      await api('/api/preferencia-consulta', {consultar_sisplan: valor});
      return true;
    } catch (erro) { $('mensagem').textContent = erro.message; return false; }
  });
  return salvamentoConsulta;
};
$('adicionar').onclick = adicionarIntervalo;
const tema = window.NunesTema.iniciar({controle:$('tema'),chave:'nunes-impressao-tema',cookie:true});
$('tema').addEventListener('click', () => { document.documentElement.dataset.temaAnimado = '1'; });
if (desktop) {
  tema.aplicar(document.querySelector('meta[name="impressao-tema"]').content);
  $('tema').addEventListener('click', () => {
    const valor = document.documentElement.dataset.tema;
    salvamentoTema = salvamentoTema.then(async () => {
      try {
        await api('/api/tema', {tema:valor}); $('tema-status').textContent = ''; return true;
      } catch (erro) { $('tema-status').textContent = erro.message; return false; }
    });
  });
}
adicionarIntervalo(); acompanhar();
