'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="impressao-token"]').content;
const desktop = document.querySelector('meta[name="impressao-desktop"]')?.content === '1';
let salvamentoTema = Promise.resolve(true);
let modo = 'intervalos', conferido = null, ocupado = false, online = false, encerrado = false, pendente = false, impressora = '';
let numeroIntervalo = 0;
let estadoAtual = null, preparando = true, resumoConferencia = null;
const pagina = crypto.randomUUID();
const presenca = new AbortController();
let ultimoEstado = '', saindo = false, historico = [];

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
  mostrarAndamento();
  $('campos').disabled = ocupado || pendente || encerrado;
  $('conferir').disabled = ocupado || pendente || !online || encerrado;
  $('imprimir').disabled = !conferido || ocupado || pendente || !online || !impressora || encerrado || historico.some(item => ['envio_iniciado', 'incerto'].includes(item.situacao));
  document.querySelectorAll('[data-conferencia]').forEach(botao => { botao.disabled = ocupado || pendente || !online || encerrado; });
  $('parar').hidden = !ocupado;
  $('selecionar-impressora').disabled = ocupado || pendente || !online || encerrado;
  $('atualizar-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('lista-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('confirmar-impressora').disabled = ocupado || pendente || !online || encerrado || !$('lista-impressoras').value;
  document.querySelectorAll('[data-modo]').forEach(botao => { botao.disabled = ocupado || pendente || encerrado; });
}
function invalidar() {
  conferido = null;
  preparando = true; resumoConferencia = null;
  $('titulo-conferencia').textContent = 'Conferência';
  $('resumo').textContent = 'Informe as OPs e confira o lote.';
  $('lotes').replaceChildren();
  const linha = document.createElement('tr'), celula = document.createElement('td');
  celula.colSpan = 3; celula.className = 'vazio'; celula.textContent = 'Aguardando conferência das OPs.';
  linha.append(celula); $('lotes').append(linha);
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
  if (modo === 'lista') return {modo, ordens: $('ordens').value, setor: $('setor-lista').value};
  return {modo, intervalos: Array.from($('intervalos').children, linha => Object.fromEntries(
    Array.from(linha.querySelectorAll('input'), input => [input.dataset.campo, input.value])))};
}
async function api(caminho, dados) {
  const resposta = await fetch(caminho, {
    method: dados === undefined ? 'GET' : 'POST',
    headers: {Authorization: `Bearer ${token}`, ...(dados === undefined ? {} : {'Content-Type': 'application/json'})},
    body: dados === undefined ? undefined : JSON.stringify(dados), signal: AbortSignal.timeout(10000)
  });
  const retorno = await resposta.json();
  if (!resposta.ok) throw Error(retorno.erro || 'Não foi possível concluir a solicitação.');
  return retorno;
}
function mostrarEstado(estado) {
  const assinatura = JSON.stringify(estado);
  if (assinatura === ultimoEstado) return;
  ultimoEstado = assinatura;
  estadoAtual = estado;
  if (estado.ocupado) preparando = false;
  ocupado = estado.ocupado; impressora = estado.impressora;
  historico = estado.historico || [];
  mostrarHistorico();
  $('impressora').textContent = impressora || 'Nenhuma impressora selecionada.';
  $('aviso-impressora').textContent = estado.aviso_impressora || '';
  $('atividade').replaceChildren();
  for (const mensagem of estado.atividade.length ? estado.atividade : ['Nenhuma OP enviada nesta execução.']) {
    const item = document.createElement('li'); item.textContent = mensagem; $('atividade').append(item);
  }
  atualizarBotoes();
}
function mostrarAndamento() {
  if (!estadoAtual) return;
  const estado = estadoAtual;
  const incertas = historico.filter(item => ['envio_iniciado', 'incerto'].includes(item.situacao)).length;
  const novoLote = preparando && !ocupado && !incertas;
  const fases = {pronto:'Pronto', imprimindo:'Em andamento', concluido:'Concluído', interrompido:'Interrompido', erro:'Conferir impressão'};
  $('fase').textContent = novoLote ? (conferido ? 'Conferido' : 'Preparação') : (fases[estado.fase] || estado.fase);
  $('fase').classList.toggle('erro', !novoLote && estado.fase === 'erro');
  $('status').textContent = novoLote ? (conferido ? 'Lote pronto para imprimir.' : 'Aguardando conferência.') : estado.mensagem;
  $('resumo-progresso').hidden = novoLote || !estado.total;
  $('ordem-atual').hidden = novoLote || !estado.atual;
  $('ordem-atual').textContent = estado.atual ? `${ocupado ? 'OP em processamento' : 'Última OP processada'}: ${estado.atual} · setor ${estado.setor}` : '';
  $('enviadas').textContent = novoLote ? 0 : estado.enviadas;
  $('total').textContent = novoLote ? 0 : estado.total;
  $('progresso').max = novoLote ? 1 : (estado.total || 1);
  $('progresso').value = novoLote ? 0 : estado.enviadas;
  $('aviso-operacao').hidden = !ocupado;
}
function mostrarHistorico() {
  const incertas = historico.filter(item => ['envio_iniciado', 'incerto'].includes(item.situacao)).length;
  $('pendencias').hidden = ocupado || !incertas;
  $('resumo-pendencias').textContent = `${incertas} OP(s) precisam de revisão. Confira a fila e o papel.`;
  $('recuperacao').replaceChildren();
  const rotulos = {pendente: 'Não iniciada', envio_iniciado: ocupado ? 'Envio em andamento' : 'Incerto: conferir fila e papel', incerto: 'Incerto: conferir fila e papel', concluido: 'Envio concluído pelo fluxo', conferido_enviado: 'Envio confirmado manualmente', conferido_nao_enviado: 'Não enviado: conferido manualmente'};
  if (!historico.length) { $('recuperacao').textContent = 'Nenhum lote salvo nesta versão.'; return; }
  for (const registro of historico) {
    const linha = document.createElement('div'); linha.className = 'registro-recuperacao';
    const descricao = document.createElement('p');
    descricao.textContent = `OP ${registro.numero} · setor ${registro.setor} · ${rotulos[registro.situacao] || registro.situacao} · ${registro.impressora || 'Impressora do console'} · ${new Date(registro.atualizado_em).toLocaleString('pt-BR')}`;
    linha.append(descricao);
    if (['envio_iniciado', 'incerto'].includes(registro.situacao)) {
      for (const [resultado, texto] of [['conferido_enviado', 'Conferi: foi enviado'], ['conferido_nao_enviado', 'Conferi: não foi enviado']]) {
        const botao = document.createElement('button'); botao.type = 'button'; botao.textContent = texto;
        botao.dataset.conferencia = registro.id;
        botao.onclick = async () => {
          if (ocupado || pendente || !online || encerrado) return;
          if (!confirm(`Você conferiu a fila e o papel da OP ${registro.numero}, setor ${registro.setor}? ${texto}. Esta ação registra sua conferência e não imprime.`)) return;
          pendente = true; atualizarBotoes(); $('erro-recuperacao').textContent = '';
          try {
            mostrarEstado(await api('/api/conferir-impressao', {id: registro.id, resultado, conferi_fila_e_papel: true}));
            invalidar();
          } catch (erro) { $('erro-recuperacao').textContent = erro.message; }
          finally { pendente = false; atualizarBotoes(); }
        };
        linha.append(botao);
      }
    }
    $('recuperacao').append(linha);
  }
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
  try {
    const dados = entrada(), resultado = await api('/api/conferir', dados);
    conferido = dados; preparando = true; resumoConferencia = resultado;
    $('titulo-conferencia').textContent = 'Conferência';
    $('lotes').replaceChildren();
    for (const lote of resultado.lotes) {
      const linha = document.createElement('tr');
      for (const valor of [lote.setor, lote.ordens.length, lote.ordens.slice(0, 100).join(' · ') + (lote.ordens.length > 100 ? ` · … e mais ${lote.ordens.length - 100} OPs` : '')]) {
        const celula = document.createElement('td'); celula.textContent = valor; linha.append(celula);
      }
      $('lotes').append(linha);
    }
    $('resumo').textContent = `${resultado.total} OPs · ${resultado.lotes.length} setor(es)`;
    $('imprimir').textContent = `Imprimir ${resultado.total} OPs`;

    $('cabecalho-conferencia').hidden = false;
    $('titulo-conferencia').focus();
  } catch (erro) { conferido = null; resumoConferencia = null; $('mensagem').textContent = erro.message; }
  finally { pendente = false; atualizarBotoes(); }
};
$('imprimir').onclick = async () => {
  if (!conferido || pendente || ocupado || encerrado || historico.some(item => ['envio_iniciado', 'incerto'].includes(item.situacao))) return;
  pendente = true; atualizarBotoes(); $('mensagem').textContent = '';
  try { const estado = await api('/api/iniciar', {...conferido, impressora}); conferido = null; preparando = false; $('titulo-conferencia').textContent = 'Lote enviado'; mostrarEstado(estado); }
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
    if (desktop && !await salvamentoTema) return;
    await api('/api/encerrar', {}); encerrado = true; online = false; atualizarBotoes();
    presenca.abort();
    $('encerrar').disabled = true; $('parar').hidden = true;
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
document.querySelectorAll('[data-modo]').forEach(botao => { botao.onclick = () => {
  modo = botao.dataset.modo;
  document.querySelectorAll('[data-modo]').forEach(outro => outro.setAttribute('aria-pressed', String(outro === botao)));
  $('modo-intervalos').hidden = modo !== 'intervalos'; $('modo-lista').hidden = modo !== 'lista'; invalidar();
}; });
$('campos').addEventListener('input', invalidar);
$('adicionar').onclick = adicionarIntervalo;
$('revisar-pendencias').onclick = () => {
  $('historico-painel').open = true;
  $('titulo-recuperacao').focus();
  $('historico-painel').scrollIntoView({block:'start', behavior:'auto'});
};
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
