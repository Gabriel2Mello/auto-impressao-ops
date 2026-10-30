"""Ensaio WebView2 isolado: sem filas reais, Sisplan, impressão ou métricas reais."""
import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
from unittest.mock import patch

from desktop_impressao import Janela, executar
from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.interface_web import criar_servidor
from src.servico_impressao import EstadoImpressao


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manter', type=int, default=0, help='Segundos para inspeção visual ao final')
    parser.add_argument('--resultado', type=Path, default=Path('.local/qa-desktop/ensaio.json'))
    args = parser.parse_args()
    evidencias, falhas = [], []
    with TemporaryDirectory(prefix='nunes-impressao-desktop-') as pasta:
        raiz = Path(pasta)
        with patch.dict(os.environ, {'NUNES_OPS_DADOS': pasta, 'NUNES_METRICAS_DADOS': str(raiz / 'metricas'),
                                     'NUNES_HUB_DADOS': str(raiz / 'hub')}), \
                patch('desktop_preferencias.arquivo', return_value=raiz / 'tema.json'), \
                patch('desktop_impressao.caminho_preferencia', return_value=raiz / 'config.json'):
            impressoras = Impressoras(raiz / 'config.json', listar=lambda: ['Fila sintética'])
            impressoras.selecionar('Fila sintética')

            def proibido(*_):
                raise AssertionError('O ensaio visual não pode executar impressão.')

            estado = EstadoImpressao(executor=proibido, impressoras=impressoras,
                                     diario=DiarioImpressao(raiz / 'diario.sqlite3'))
            servidor, _ = criar_servidor(estado, porta=0, modo_desktop=True)

            class Ensaio(Janela):
                def executar(self):
                    def verificar():
                        import webview
                        try:
                            limite = time.monotonic() + 40
                            while not webview.windows:
                                if time.monotonic() > limite:
                                    raise RuntimeError('Janela ausente')
                                time.sleep(.1)
                            janela = webview.windows[0]
                            assert janela.events.loaded.wait(30), 'Página não carregou'
                            from System.Drawing import Size
                            janela.native.MinimumSize = Size(300, 300)
                            for _ in range(100):
                                if janela.evaluate_js('online'):
                                    break
                                time.sleep(.1)
                            assert janela.evaluate_js('online'), 'Canal de presença não iniciou'
                            # Restaurar o tema não anima; a primeira troca manual habilita o efeito.
                            assert janela.evaluate_js("!document.documentElement.hasAttribute('data-tema-animado')"), 'Tema inicial animado'
                            for _ in range(2):
                                efeito = janela.evaluate_js("""(() => {
                                  document.getElementById('tema').click();
                                  const css=getComputedStyle(document.body);
                                  return {reduzido:matchMedia('(prefers-reduced-motion: reduce)').matches,
                                    duracao:css.transitionDuration,
                                    icone:getComputedStyle(document.getElementById('tema'),'::before').animationDuration};
                                })()""")
                                assert all(valor.strip() == ('0s' if efeito['reduzido'] else '0.15s') for valor in efeito['duracao'].split(',')), efeito
                                assert efeito['icone'] == ('0s' if efeito['reduzido'] else '0.12s'), efeito
                                time.sleep(.25)
                            from System import Action
                            janela.native.Invoke(Action(lambda: janela.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(
                                'Emulation.setEmulatedMedia', '{"features":[{"name":"prefers-reduced-motion","value":"reduce"}]}')))
                            for _ in range(30):
                                if janela.evaluate_js("matchMedia('(prefers-reduced-motion: reduce)').matches"):
                                    break
                                time.sleep(.1)
                            assert janela.evaluate_js("matchMedia('(prefers-reduced-motion: reduce)').matches"), 'Emulação de movimento reduzido ausente'
                            janela.evaluate_js("document.getElementById('tema').click()")
                            assert janela.evaluate_js("getComputedStyle(document.body).transitionDuration === '0s' && getComputedStyle(document.getElementById('tema'),'::before').animationName === 'none'"), 'Movimento reduzido não respeitado'
                            janela.native.Invoke(Action(lambda: janela.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(
                                'Emulation.setEmulatedMedia', '{"features":[]}')))
                            # Descendentes de regiões ocultas não acumulam transições de cor.
                            assert janela.evaluate_js("getComputedStyle(document.getElementById('lista-impressoras')).transitionDuration === '0s'"), 'Diálogo com transição tardia'
                            # O mesmo ambiente deve carregar o adaptador existente de 32 bits.
                            from src import handle_app
                            assert handle_app.CAMPOS['numero'] == 5
                            for largura, altura in [(1180, 820), (1920, 1000), (1000, 720), (760, 600), (360, 780)]:
                                janela.resize(largura, altura)
                                time.sleep(.3)
                                for tema in ['claro', 'escuro']:
                                    janela.evaluate_js(f'tema.aplicar({json.dumps(tema)})')
                                    for excedente in [False, True]:
                                        janela.evaluate_js("document.getElementById('resultados').replaceChildren()")
                                        if excedente:
                                            janela.evaluate_js("for(let i=0;i<80;i++){const p=document.createElement('p');p.textContent='OP sintética '+i;document.getElementById('resultados').append(p)}")
                                        time.sleep(.15)
                                        medidas = janela.evaluate_js("({largura:innerWidth,altura:innerHeight,excesso:document.documentElement.scrollWidth>document.documentElement.clientWidth,rodape:document.querySelector('footer').getBoundingClientRect().width,conteudo:document.querySelector('main').getBoundingClientRect().width,barra:getComputedStyle(document.documentElement).scrollbarGutter})")
                                        assert not medidas['excesso'], medidas
                                        assert abs(medidas['rodape'] - medidas['largura']) < 2, medidas
                                        assert medidas['barra'] != 'stable', medidas
                                        for forma in ['lista', 'intervalos']:
                                            janela.evaluate_js(f"document.querySelector('[data-modo={forma}]').click()")
                                            layout = janela.evaluate_js("""(() => {
                                              const rect=s=>document.querySelector(s).getBoundingClientRect();
                                              const p=rect('.painel-impressora'),e=rect('.entrada'),c=rect('.conferencia'),l=rect('.lateral'),principal=rect('.principal');
                                              return {largura:innerWidth,impressoraTopo:p.top,impressoraFim:p.bottom,impressoraDireita:p.right,
                                                entradaTopo:e.top,entradaEsquerda:e.left,conferenciaFim:c.bottom,preparacaoFim:rect('.preparacao').bottom,lateralTopo:l.top,
                                                divisoria:l.left,divisoriaEsperada:(principal.left+principal.right)/2+14,
                                                excesso:document.documentElement.scrollWidth>document.documentElement.clientWidth,
                                                fundo:getComputedStyle(document.querySelector('.preparacao')).backgroundColor};
                                            })()""")
                                            if forma == 'lista':
                                                assert janela.evaluate_js("(() => {const s=document.getElementById('setor-lista').getBoundingClientRect(),b=document.getElementById('conferir').getBoundingClientRect();return Math.abs(s.bottom-b.bottom)<1 && Math.abs(s.top-b.top)<1})()"), 'Conferir OPs não alinha com o setor'
                                            assert not layout['excesso'], layout
                                            assert layout['fundo'] == 'rgba(0, 0, 0, 0)', layout
                                            assert layout['impressoraFim'] <= layout['entradaTopo'], layout
                                            if layout['largura'] <= 700:
                                                assert layout['lateralTopo'] >= layout['preparacaoFim'], layout
                                            else:
                                                assert abs(layout['divisoria'] - layout['divisoriaEsperada']) < 1, layout
                                        evidencias.append(dict(tema=tema, excedente=excedente, **medidas))
                            # A barra sobreposta não muda a geometria ao aparecer.
                            janela.resize(1180, 820)
                            janela.evaluate_js("document.getElementById('resultados').replaceChildren();window.scrollTo(0,0)")
                            antes = janela.evaluate_js("document.querySelector('.preparacao').getBoundingClientRect().width")
                            janela.evaluate_js("for(let i=0;i<80;i++){const p=document.createElement('p');p.textContent='OP sintética '+i;document.getElementById('resultados').append(p)}")
                            time.sleep(.2)
                            assert janela.evaluate_js("document.getElementById('resultados').scrollHeight > document.getElementById('resultados').clientHeight && document.documentElement.scrollHeight <= innerHeight + 1"), 'Resultados expandiram a página'
                            janela.evaluate_js("document.getElementById('resultados').scrollTop=100")
                            assert janela.evaluate_js("document.getElementById('resultados').scrollTop > 0 && window.scrollY === 0"), 'Rolagem independente ausente'
                            depois = janela.evaluate_js("document.querySelector('.preparacao').getBoundingClientRect().width")
                            assert abs(antes - depois) < 1, (antes, depois)
                            janela.evaluate_js("document.getElementById('resultados').replaceChildren()")
                            assert janela.evaluate_js("document.getElementById('resumo-progresso').hidden"), 'Progresso vazio visível'
                            time.sleep(.15)
                            assert janela.evaluate_js("""(() => {
                              const lateral=document.querySelector('.lateral').getBoundingClientRect();
                              return !Array.from(document.querySelectorAll('.barra-rolagem')).some(b=>{
                                const r=b.getBoundingClientRect();
                                return !b.hidden && r.left>=lateral.left && r.right<=lateral.right;
                              });
                            })()"""), 'Barra de região recolhida visível'

                            # Intervalos excedentes rolam só abaixo dos modos, mantendo a página fixa.
                            janela.evaluate_js("for(let i=0;i<15;i++) adicionarIntervalo()")
                            time.sleep(.2)
                            assert janela.evaluate_js("(() => {const r=document.querySelector('.rolagem-preparacao');return r.scrollHeight>r.clientHeight && document.documentElement.scrollHeight<=innerHeight+1})()"), 'Preparação expandiu a página'
                            assert janela.evaluate_js("""(() => {
                              const r=document.querySelector('.rolagem-preparacao').getBoundingClientRect();
                              const limite=document.querySelector('.lateral').getBoundingClientRect().left;
                              return Array.from(document.querySelectorAll('.barra-rolagem')).some(b=>{
                                const t=b.getBoundingClientRect();
                                return !b.hidden && Math.abs(t.top-r.top)<1 && t.left>=r.right-.5 && t.right<=limite;
                              });
                            })()"""), 'Barra da preparação sobrepõe os controles'
                            topo_modos = janela.evaluate_js("document.querySelector('.modos').getBoundingClientRect().top")
                            janela.evaluate_js("document.querySelector('.rolagem-preparacao').scrollTop=200")
                            assert janela.evaluate_js("document.querySelector('.rolagem-preparacao').scrollTop>0 && window.scrollY===0"), 'Preparação sem rolagem independente'
                            assert janela.evaluate_js("document.querySelector('.modos').getBoundingClientRect().top") == topo_modos, 'Modos deslocaram'
                            janela.evaluate_js("document.querySelectorAll('.intervalo').forEach((r,i)=>{if(i)r.remove()});document.querySelector('.rolagem-preparacao').scrollTop=0;invalidar()")

                            # Contadores fixos e lista próxima ao último elemento visível.
                            assert janela.evaluate_js("""(() => {
                              const anterior=estadoAtual;
                              const geometria=()=>['.indicadores'].map(s=>document.querySelector(s).getBoundingClientRect().top);
                              const antes=geometria();
                              let ok=true;
                              for(const estado of [
                                {...anterior,ocupado:true,total:5,enviadas:0,atual:'',fase:'imprimindo',mensagem:'Conectando ao Sisplan…'},
                                {...anterior,ocupado:true,total:5,enviadas:3,atual:'123459',setor:'10',fase:'imprimindo',mensagem:'Enviando OP 123459 · setor 10'},
                                {...anterior,ocupado:false,total:5,enviadas:5,atual:'123460',setor:'10',fase:'concluido',mensagem:'Todas as OPs foram enviadas para impressão.'}]) {
                                mostrarEstado(estado);
                                ok=ok && geometria().every((v,i)=>Math.abs(v-antes[i])<1);
                                const rect=s=>document.querySelector(s).getBoundingClientRect();
                                const fim=rect(estado.ocupado ? '.controles-execucao' : '#resumo-progresso');
                                ok=ok && Math.abs(rect('#resultados').top-fim.bottom-12)<1;
                                ok=ok && Math.abs(rect('#resumo-progresso').top-rect('.estado-execucao').bottom-8)<1;
                                ok=ok && Math.abs(rect('.andamento').top-rect('.indicadores').bottom-16)<1;
                              }
                              ok=ok && document.documentElement.scrollHeight<=innerHeight+1 && document.querySelector(".andamento").getBoundingClientRect().height<180;
                              mostrarEstado(anterior);
                              return ok;
                            })()"""), 'Posição dos cartões ou espaçamento do acompanhamento incorreto'

                            from System import Action
                            janela.maximize()
                            time.sleep(.3)
                            janela.native.Invoke(Action(lambda: setattr(janela.native.webview, 'ZoomFactor', 2.0)))
                            time.sleep(.3)
                            medidas = janela.evaluate_js('({largura:innerWidth,excesso:document.documentElement.scrollWidth>document.documentElement.clientWidth})')
                            assert not medidas['excesso'], medidas
                            evidencias.append(dict(zoom=2, maximizada=True, **medidas))
                            janela.native.Invoke(Action(lambda: setattr(janela.native.webview, 'ZoomFactor', 1.0)))
                            janela.restore()
                            janela.resize(1180, 820)
                            janela.evaluate_js("document.getElementById('resultados').replaceChildren();document.getElementById('ordens').value='123456\\n123457';modo='lista';document.getElementById('modo-lista').hidden=false;document.getElementById('modo-intervalos').hidden=true")
                            janela.evaluate_js("document.getElementById('conferir').click()")
                            for _ in range(50):
                                if janela.evaluate_js('conferido !== null'):
                                    break
                                time.sleep(.1)
                            assert janela.evaluate_js('conferido !== null && !document.getElementById("imprimir").disabled'), 'Conferência indisponível'
                            assert janela.evaluate_js("!document.getElementById('tabela-conferencia').hidden && document.getElementById('imprimir').textContent === 'Imprimir 2 OPs'"), 'Resumo conferido ausente'
                            assert janela.evaluate_js("document.querySelector('[data-aba=conferencia]').getAttribute('aria-pressed') === 'true' && !document.getElementById('modo-conferencia').hidden && document.getElementById('formulario').hidden && document.activeElement.id === 'titulo-conferencia'"), 'Aba Conferência não ativada'
                            janela.evaluate_js("document.querySelector('[data-aba=lista]').click()")
                            assert janela.evaluate_js("!document.getElementById('modo-lista').hidden && conferido !== null"), 'Voltar à entrada perdeu o lote'
                            assert estado.worker is None, 'Conferência iniciou executor'
                            janela.evaluate_js("document.getElementById('ordens').value='123458';document.getElementById('ordens').dispatchEvent(new Event('input',{bubbles:true}))")
                            assert janela.evaluate_js('conferido === null && document.getElementById("imprimir").disabled'), 'Edição não invalidou conferência'
                            # Persistência pelo servidor real, inclusive com o WebView em modo privado.
                            janela.evaluate_js("document.getElementById('tema').click()")
                            for _ in range(50):
                                if (raiz / 'tema.json').exists():
                                    break
                                time.sleep(.1)
                            assert (raiz / 'tema.json').exists(), 'Tema não persistido'
                            janela.evaluate_js("document.getElementById('selecionar-impressora').click()")
                            time.sleep(.3)
                            assert janela.evaluate_js('document.getElementById("dialogo-impressora").open'), 'Diálogo ausente'
                            janela.evaluate_js("document.getElementById('cancelar-impressora').click()")
                            janela.evaluate_js("tema.aplicar('escuro');document.querySelectorAll('[data-modo]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.modo==='lista')));window.scrollTo(0,0)")
                            if args.manter:
                                time.sleep(args.manter)
                        except Exception as erro:
                            falhas.append(repr(erro))
                        finally:
                            servidor.encerrar()
                    thread = Thread(target=verificar, name='impressao-ensaio')
                    thread.start()
                    try:
                        super().executar()
                    finally:
                        thread.join()

            try:
                executar(servidor, fabrica=Ensaio)
            finally:
                servidor.server_close()
                args.resultado.parent.mkdir(parents=True, exist_ok=True)
                args.resultado.write_text(json.dumps({'cenarios': evidencias, 'falhas': falhas}, ensure_ascii=False, indent=2), encoding='utf-8')
    if falhas:
        raise RuntimeError('; '.join(falhas))
    print(f'WebView2: {len(evidencias)} cenários aprovados; conferência, invalidação, tema e diálogo aprovados.')


if __name__ == '__main__':
    main()
