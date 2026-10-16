'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="impressao-token"]').content;
let modo = 'intervalos', conferido = null, ocupado = false, online = false, encerrado = false, pendente = false, impressora = '';
let numeroIntervalo = 0;
const pagina = crypto.randomUUID();
const presenca = new AbortController();
let ultimoEstado = '', saindo = false;

function atualizarBotoes() {
  $('campos').disabled = ocupado || pendente || encerrado;
  $('conferir').disabled = ocupado || pendente || !online || encerrado;
  $('imprimir').disabled = !conferido || ocupado || pendente || !online || !impressora || encerrado;
  $('parar').hidden = !ocupado;
  $('selecionar-impressora').disabled = ocupado || pendente || !online || encerrado;
  $('atualizar-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('lista-impressoras').disabled = ocupado || pendente || !online || encerrado;
  $('confirmar-impressora').disabled = ocupado || pendente || !online || encerrado || !$('lista-impressoras').value;
  document.querySelectorAll('[data-modo]').forEach(botao => { botao.disabled = ocupado || pendente || encerrado; });
}
function invalidar() {
  conferido = null;
  $('resumo').textContent = 'Confira o lote para atualizar as OPs antes de imprimir.';
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
  for (const [chave, titulo, valor] of [['de', 'De', ''], ['para', 'Para', ''], ['setor', 'Setor', '10']]) {
    const grupo = document.createElement('div'), label = document.createElement('label'), input = document.createElement('input');
    input.id = `${chave}-${numero}`; input.dataset.campo = chave; input.inputMode = 'numeric';
    input.maxLength = chave === 'setor' ? 6 : 12; input.autocomplete = 'off'; input.value = valor;
    input.placeholder = chave === 'de' ? 'Ex.: 123456' : chave === 'para' ? 'Mesma OP' : '10';
    label.htmlFor = input.id; label.textContent = titulo; grupo.append(label, input); linha.append(grupo);
  }
  const remover = document.createElement('button'); remover.type = 'button'; remover.textContent = 'Remover';
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
  ocupado = estado.ocupado; impressora = estado.impressora;
  const fases = {pronto: 'Pronto', imprimindo: 'Em andamento', concluido: 'Concluído', interrompido: 'Interrompido', erro: 'Conferir impressão'};
  $('fase').textContent = fases[estado.fase] || estado.fase;
  $('fase').classList.toggle('erro', estado.fase === 'erro');
  $('status').textContent = estado.mensagem;
  $('ordem-atual').textContent = estado.atual ? `Última OP em processamento: ${estado.atual} · setor ${estado.setor}` : 'Informe as ordens e confira o lote antes de imprimir.';
  $('enviadas').textContent = estado.enviadas; $('total').textContent = estado.total;
  $('progresso').max = estado.total || 1; $('progresso').value = estado.enviadas;
  $('impressora').textContent = impressora ? `Impressora: ${impressora}` : 'Nenhuma impressora selecionada. Clique em Selecionar impressora.';
  $('aviso-impressora').textContent = estado.aviso_impressora || '';
  $('atividade').replaceChildren();
  for (const mensagem of estado.atividade.length ? estado.atividade : ['Nenhuma OP enviada nesta execução.']) {
    const item = document.createElement('li'); item.textContent = mensagem; $('atividade').append(item);
  }
  atualizarBotoes();
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
    $('conexao').textContent = 'Painel conectado · neste computador';
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
    conferido = dados; $('lotes').replaceChildren();
    for (const lote of resultado.lotes) {
      const linha = document.createElement('tr');
      for (const valor of [lote.setor, lote.ordens.length, lote.ordens.slice(0, 100).join(' · ') + (lote.ordens.length > 100 ? ` · … e mais ${lote.ordens.length - 100} OPs` : '')]) {
        const celula = document.createElement('td'); celula.textContent = valor; linha.append(celula);
      }
      $('lotes').append(linha);
    }
    $('resumo').textContent = `${resultado.total} OPs · ${resultado.lotes.length} lote(s) por setor. Confira os números e clique em Imprimir lote.`;
    $('titulo-conferencia').focus();
  } catch (erro) { conferido = null; $('mensagem').textContent = erro.message; }
  finally { pendente = false; atualizarBotoes(); }
};
$('imprimir').onclick = async () => {
  if (!conferido || pendente || ocupado || encerrado) return;
  pendente = true; atualizarBotoes(); $('mensagem').textContent = '';
  try { const estado = await api('/api/iniciar', {...conferido, impressora}); conferido = null; mostrarEstado(estado); }
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
    await api('/api/encerrar', {}); encerrado = true; online = false; atualizarBotoes();
    presenca.abort();
    $('encerrar').disabled = true; $('parar').hidden = true;
    $('status').textContent = ocupado ? 'Encerrando após a OP em andamento. Você pode fechar esta aba.' : 'Programa encerrado. Você pode fechar esta aba.';
    $('conexao').textContent = 'Painel encerrado';
  } catch (erro) { $('mensagem').textContent = erro.message; }
};
window.addEventListener('beforeunload', evento => {
  if (encerrado) return;
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
const sistemaEscuro = matchMedia('(prefers-color-scheme: dark)');
function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  $('tema').textContent = tema === 'escuro' ? 'Tema claro' : 'Tema escuro';
}
let temaSalvo = null;
try { temaSalvo = localStorage.getItem('nunes-impressao-tema'); } catch { /* Preferência indisponível: usar o sistema. */ }
aplicarTema(['claro', 'escuro'].includes(temaSalvo) ? temaSalvo : sistemaEscuro.matches ? 'escuro' : 'claro');
$('tema').onclick = () => {
  temaSalvo = document.documentElement.dataset.tema === 'escuro' ? 'claro' : 'escuro'; aplicarTema(temaSalvo);
  try { localStorage.setItem('nunes-impressao-tema', temaSalvo); } catch { /* O tema continua ativo nesta aba. */ }
};
sistemaEscuro.addEventListener('change', () => { if (!temaSalvo) aplicarTema(sistemaEscuro.matches ? 'escuro' : 'claro'); });
adicionarIntervalo(); acompanhar();
