"""Uma execução por vez, com parada entre OPs e integração Windows tardia."""

import logging
from threading import Event, Lock, Thread

from src.entrada_web import montar_lotes
from src.utils import obter_caminho_impressora


def executar_lotes(lotes, parar, atualizar):
    from main import processar_ordem
    from src.handle_app import inicia_app, preencher_dados_fixos

    if parar.is_set():
        return
    app, campos = inicia_app()
    for lote in lotes:
        if parar.is_set():
            return
        preencher_dados_fixos(campos, lote['setor'])
        for numero in lote['ordens']:
            if parar.is_set():
                return
            atualizar('atual', numero, lote['setor'])
            # Uma falha pode ocorrer após o envio: não repetir impressão automaticamente.
            processar_ordem(app, campos, numero, max_tentativas=1)
            atualizar('enviada', numero, lote['setor'])


class ConflitoExecucao(RuntimeError):
    pass


class EstadoImpressao:
    def __init__(self, executor=executar_lotes):
        self.trava = Lock()
        self.parar = Event()
        self.worker = None
        self.executor = executor
        self.encerrando = False
        self.dados = {
            'fase': 'pronto', 'mensagem': 'Pronto para conferir as OPs.',
            'total': 0, 'enviadas': 0, 'atual': '', 'setor': '', 'atividade': [],
        }

    def situacao(self):
        with self.trava:
            dados = dict(self.dados, atividade=list(self.dados['atividade']),
                         ocupado=self.worker is not None and self.worker.is_alive())
        try:
            dados['impressora'] = obter_caminho_impressora()
        except RuntimeError:
            dados['impressora'] = ''
        return dados

    def iniciar(self, entrada):
        lotes = montar_lotes(entrada)
        obter_caminho_impressora()
        with self.trava:
            if self.encerrando or (self.worker is not None and self.worker.is_alive()):
                raise ConflitoExecucao('Aguarde o término da execução atual.')
            self.parar.clear()
            self.dados = {
                'fase': 'imprimindo', 'mensagem': 'Conectando ao Sisplan…',
                'total': sum(len(lote['ordens']) for lote in lotes),
                'enviadas': 0, 'atual': '', 'setor': '', 'atividade': [],
            }
            self.worker = Thread(target=self._executar, args=(lotes,), daemon=False)
            self.worker.start()

    def _atualizar(self, evento, numero, setor):
        with self.trava:
            self.dados.update(atual=numero, setor=setor)
            if evento == 'enviada':
                self.dados['enviadas'] += 1
                self.dados['atividade'].append(f'OP {numero} · setor {setor} · enviada para impressão')
                self.dados['atividade'] = self.dados['atividade'][-50:]
            else:
                self.dados['mensagem'] = f'Enviando OP {numero} · setor {setor}'

    def _executar(self, lotes):
        try:
            self.executor(lotes, self.parar, self._atualizar)
        except Exception as erro:
            logging.exception('Falha na impressão de OPs')
            with self.trava:
                self.dados.update(fase='erro', mensagem=f'{erro} Confira a última OP na impressora antes de iniciar outra execução.')
        else:
            with self.trava:
                interrompido = self.dados['enviadas'] < self.dados['total']
                self.dados.update(
                    fase='interrompido' if interrompido else 'concluido',
                    mensagem='Processamento interrompido entre OPs.' if interrompido else 'Todas as OPs foram enviadas para impressão.',
                )

    def solicitar_parada(self):
        with self.trava:
            self.parar.set()
            if self.worker is not None and self.worker.is_alive():
                self.dados['mensagem'] = 'Parada solicitada. Aguardando a OP em andamento.'

    def encerrar(self):
        with self.trava:
            self.encerrando = True
            self.parar.set()
