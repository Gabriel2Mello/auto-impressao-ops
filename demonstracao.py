"""Interface real com executor e impressoras fictícios, sem publicação no Hub."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.servico_impressao import EstadoImpressao

CONTROLES = '''<section class="demonstracao" aria-label="Demonstração">
<div><strong>Demonstração</strong><p>Dados fictícios · sem Sisplan ou impressão real</p></div>
<label>Resultado simulado<select id="demo-resultado"><option value="sucesso">Conclusão normal</option><option value="erro">Falha durante o envio</option></select></label>
<button id="demo-exemplo" type="button">Preencher exemplo</button>
<span id="demo-mensagem" role="status"></span>
</section><script src="/demonstracao.js" defer></script>'''


class DiarioDemonstracao(DiarioImpressao):
    def publicar_metricas(self):
        # O diário mantém o mesmo contrato, mas nunca publica estatísticas de teste.
        pass


class EstadoDemonstracao(EstadoImpressao):
    def __init__(self, pasta, atraso=.8):
        self.cenario = 'sucesso'
        self.atraso = atraso
        filas = ['EPSON L4260 · Demonstração', 'Impressora de produção · Demonstração']
        impressoras = Impressoras(Path(pasta) / 'impressora.json', listar=lambda: filas)
        impressoras.selecionar(filas[0])
        super().__init__(executor=self.simular, impressoras=impressoras,
                         diario=DiarioDemonstracao(Path(pasta) / 'diario.sqlite3'))

    def configurar_demo(self, dados):
        with self.trava:
            self._exigir_disponivel()
            if dados.get('resultado') not in ('sucesso', 'erro'):
                raise ValueError('Resultado simulado inválido.')
            self.cenario = dados['resultado']

    def simular(self, lotes, parar, atualizar, impressora):
        for lote in lotes:
            for numero in lote['ordens']:
                if parar.is_set():
                    return
                atualizar('atual', numero, lote['setor'])
                time.sleep(self.atraso)
                if self.cenario == 'erro':
                    raise RuntimeError('Falha simulada durante o envio da OP.')
                atualizar('enviada', numero, lote['setor'])


def main():
    from desktop_impressao import executar
    from src.interface_web import criar_servidor

    with TemporaryDirectory(prefix='nunes-impressao-demo-') as pasta:
        # Isola também tema, geometria, diagnóstico e qualquer métrica auxiliar.
        variaveis = {'LOCALAPPDATA': str(Path(pasta) / 'local'),
                     'NUNES_OPS_DADOS': pasta, 'NUNES_HUB_DADOS': str(Path(pasta) / 'hub'),
                     'NUNES_METRICAS_DADOS': str(Path(pasta) / 'metricas')}
        anteriores = {chave: os.environ.get(chave) for chave in variaveis}
        os.environ.update(variaveis)
        try:
            servidor, _ = criar_servidor(EstadoDemonstracao(pasta), porta=0, modo_desktop=True)
            servidor.demonstracao = True
            try:
                executar(servidor)
            finally:
                servidor.server_close()
        finally:
            for chave, valor in anteriores.items():
                if valor is None:
                    os.environ.pop(chave, None)
                else:
                    os.environ[chave] = valor
    return 0
