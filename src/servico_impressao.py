"""Uma execução por vez, com parada entre OPs e integração Windows tardia."""

import logging
from contextlib import nullcontext

from threading import Event, Lock, Thread

from src.entrada_web import montar_lotes
from src.impressoras import Impressoras
from src.diario_impressao import DiarioImpressao


def executar_lotes(lotes, parar, atualizar, impressora=None):
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
            processar_ordem(app, campos, numero, impressora=impressora)
            atualizar('enviada', numero, lote['setor'])


class ConflitoExecucao(RuntimeError):
    pass


class EstadoImpressao:
    def __init__(self, executor=executar_lotes, impressoras=None, diario=None, medidor_abertura=None):
        with medidor_abertura.etapa('diario_local') if medidor_abertura is not None else nullcontext():
            self.diario = diario if diario is not None else DiarioImpressao()
        self.execucao = None
        self.trava = Lock()
        self.parar = Event()
        self.worker = None
        self.executor = executor
        with medidor_abertura.etapa('impressoras_windows') if medidor_abertura is not None else nullcontext():
            self.impressoras = impressoras if impressoras is not None else Impressoras()
        self.impressora_lote = ''
        self.uso_registrado = False
        self.encerrando = False
        self.dados = {
            'fase': 'pronto', 'mensagem': 'Pronto para conferir as OPs.',
            'total': 0, 'enviadas': 0, 'atual': '', 'setor': '', 'atividade': [],
        }

    def situacao(self):
        with self.trava:
            dados = dict(self.dados, atividade=list(self.dados['atividade']),
                         ocupado=self.worker is not None and self.worker.is_alive())
            dados.update(self.impressoras.situacao())
            dados['historico'] = self.diario.consultar()
            incertas = sum(item['situacao'] in ('envio_iniciado', 'incerto') for item in dados['historico'])
            if incertas and not dados['ocupado']:
                dados.update(fase='erro', mensagem=f'Há {incertas} OP(s) com resultado incerto. '
                             'Confira a fila e o papel em Histórico e recuperação antes de iniciar outro lote.')
        return dados

    def listar_impressoras(self):
        with self.trava:
            self._exigir_disponivel()
            return dict(self.impressoras.atualizar(), impressoras=list(self.impressoras.nomes))

    def _exigir_disponivel(self):
        if self.encerrando or (self.worker is not None and self.worker.is_alive()):
            raise ConflitoExecucao('Aguarde o término da execução atual.')

    def selecionar_impressora(self, nome):
        with self.trava:
            self._exigir_disponivel()
            self.impressoras.selecionar(nome)

    def iniciar(self, entrada):
        lotes = montar_lotes(entrada)
        with self.trava:
            self._exigir_disponivel()
            nome = self.impressoras.validar(entrada.get('impressora'))
            if nome != self.impressoras.selecionada:
                raise ConflitoExecucao('A impressora foi alterada em outra aba. Confira a impressora selecionada antes de imprimir.')
            self.execucao = self.diario.iniciar(lotes, nome)
            self.impressora_lote = nome
            self.uso_registrado = False
            self.parar.clear()
            self.dados = {
                'fase': 'imprimindo', 'mensagem': 'Conectando ao Sisplan…',
                'total': sum(len(lote['ordens']) for lote in lotes),
                'enviadas': 0, 'atual': '', 'setor': '', 'atividade': [],
            }
            self.worker = Thread(target=self._executar, args=(lotes,), daemon=False)
            self.worker.start()

    def conferir_impressao(self, dados):
        with self.trava:
            self._exigir_disponivel()
            if dados.get('conferi_fila_e_papel') is not True:
                raise ValueError('Confirme a conferência da fila e do papel.')
            self.diario.conferir(dados.get('id'), dados.get('resultado'))

    def _atualizar(self, evento, numero, setor):
        with self.trava:
            self.diario.atualizar(self.execucao, numero, setor,
                                  'concluido' if evento == 'enviada' else 'envio_iniciado')
            self.dados.update(atual=numero, setor=setor)
            if evento == 'enviada':
                self.dados['enviadas'] += 1
                if not self.uso_registrado:
                    self.uso_registrado = True
                    self.impressoras.registrar_uso(self.impressora_lote)
                self.dados['atividade'].append(f'OP {numero} · setor {setor} · enviada para impressão')
                self.dados['atividade'] = self.dados['atividade'][-50:]
            else:
                self.dados['mensagem'] = f'Enviando OP {numero} · setor {setor}'

    def _executar(self, lotes):
        try:
            self.executor(lotes, self.parar, self._atualizar, self.impressora_lote)
        except Exception as erro:
            logging.exception('Falha na impressão de OPs')
            try:
                self.diario.interromper(self.execucao)
            except RuntimeError:
                logging.exception('Falha ao registrar interrupção; o início persistido continua incerto')
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
