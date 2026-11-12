"""Uma execução por vez, com parada entre OPs e integração Windows tardia."""

import logging
from contextlib import nullcontext
from copy import deepcopy
from secrets import token_urlsafe

from threading import Event, Lock, Thread

from integracao_hub import SisplanOcupado
from src.entrada_web import analisar_pedidos, montar_lotes
from src.impressoras import Impressoras
from src.diario_impressao import DiarioImpressao
from src.cliente_consulta_ops import consultar_localizacoes, consultar_pedidos
from src.preferencias_impressao import ler_consulta, salvar_consulta


def executar_lotes(lotes, parar, atualizar, impressora=None):
    from main import processar_ordem
    from src.handle_app import inicia_app, preencher_dados_fixos

    if parar.is_set():
        return
    app, campos = inicia_app()
    for lote in lotes:
        if parar.is_set():
            return
        if 'faccao' in lote:
            preencher_dados_fixos(campos, lote['setor'], faccao=lote['faccao'])
        else:
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
    def __init__(self, executor=executar_lotes, impressoras=None, diario=None, medidor_abertura=None,
                 consultar=consultar_localizacoes, buscar_pedidos=consultar_pedidos,
                 *, exigir_conferencia=False, reservar_sisplan=None):
        with medidor_abertura.etapa('diario_local') if medidor_abertura is not None else nullcontext():
            self.diario = diario if diario is not None else DiarioImpressao()
        self.execucao = None
        self.trava = Lock()
        self.parar = Event()
        self.worker = None
        self.executor = executor
        self.consultar = consultar
        self.buscar_pedidos = buscar_pedidos
        self.exigir_conferencia = exigir_conferencia
        self.reservar_sisplan = reservar_sisplan
        self.conferencia_sisplan = None
        with medidor_abertura.etapa('impressoras_windows') if medidor_abertura is not None else nullcontext():
            self.impressoras = impressoras if impressoras is not None else Impressoras()
        self.arquivo_consulta = self.impressoras.caminho.with_name('conferencia.json')
        self.consultar_sisplan = ler_consulta(self.arquivo_consulta)
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
            dados['historico'] = self.diario.consultar(apenas_ultimo=True)
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

    def preferencia_consulta(self):
        with self.trava:
            return self.consultar_sisplan

    def selecionar_consulta(self, valor):
        with self.trava:
            if self.encerrando:
                raise ConflitoExecucao('O programa está encerrando.')
            salvar_consulta(self.arquivo_consulta, valor)
            self.consultar_sisplan = valor

    def iniciar(self, entrada):
        por_pedido = isinstance(entrada, dict) and entrada.get('modo') == 'pedido'
        original = analisar_pedidos(entrada) if por_pedido else montar_lotes(entrada)
        automatico = por_pedido or entrada.get('consultar_sisplan', False)
        consulta = self.buscar_pedidos if por_pedido else self.consultar
        lotes = original
        with self.trava:
            self._exigir_disponivel()
            conferencia = self.conferencia_sisplan
            self.conferencia_sisplan = None
            if automatico or self.exigir_conferencia:
                if (conferencia is None or entrada.get('conferencia_id') != conferencia['id']
                        or original != conferencia['entrada']):
                    raise ConflitoExecucao('Confira novamente as OPs no Sisplan antes de imprimir.')
                lotes = conferencia['lotes']
            grupos = entrada.get('grupos_selecionados')
            selecionados = lotes
            if por_pedido or 'grupos_selecionados' in entrada:
                if (not isinstance(grupos, list) or not 1 <= len(grupos) <= len(lotes)
                        or any(type(i) is not int or not 0 <= i < len(lotes) for i in grupos)
                        or len(set(grupos)) != len(grupos)):
                    raise ValueError('Selecione pelo menos um grupo válido para imprimir.')
                indices = set(grupos)
                selecionados = [lote for indice, lote in enumerate(lotes) if indice in indices]
            if automatico:
                atuais = consulta(original)
                if atuais != conferencia['lotes']:
                    raise ConflitoExecucao('As OPs ou suas localizações mudaram no Sisplan. Confira novamente antes de imprimir.')
            lotes = selecionados
            nome = self.impressoras.validar(entrada.get('impressora'))
            if nome != self.impressoras.selecionada:
                raise ConflitoExecucao('A impressora foi alterada em outra aba. Confira a impressora selecionada antes de imprimir.')
            try:
                reserva = self.reservar_sisplan() if self.reservar_sisplan else None
            except SisplanOcupado:
                self.conferencia_sisplan = conferencia
                raise

            def executar():
                try:
                    self._executar(lotes)
                finally:
                    if reserva is not None:
                        reserva.fechar()

            try:
                self.execucao = self.diario.iniciar(lotes, nome, exigir_conferencia=False)
                self.impressora_lote = nome
                self.uso_registrado = False
                self.parar.clear()
                self.dados = {
                    'fase': 'imprimindo', 'mensagem': 'Conectando ao Sisplan…',
                    'total': sum(len(lote['ordens']) for lote in lotes),
                    'enviadas': 0, 'atual': '', 'setor': '', 'atividade': [],
                }
                self.worker = Thread(target=executar, daemon=False)
                try:
                    self.worker.start()
                except RuntimeError:
                    self.worker = None
                    self.dados.update(fase='erro', mensagem='Não foi possível iniciar o lote.')
                    self.diario.interromper(self.execucao)
                    raise
            except BaseException:
                if reserva is not None:
                    reserva.fechar()
                raise

    def conferir(self, entrada):
        por_pedido = isinstance(entrada, dict) and entrada.get('modo') == 'pedido'
        lotes = analisar_pedidos(entrada) if por_pedido else montar_lotes(entrada)
        consulta = self.buscar_pedidos if por_pedido else self.consultar
        with self.trava:
            self._exigir_disponivel()
            self.conferencia_sisplan = None
            conferencia_id = None
            automatico = por_pedido or entrada.get('consultar_sisplan', False)
            if automatico or self.exigir_conferencia:
                originais = deepcopy(lotes)
                if automatico:
                    lotes = consulta(lotes)
                conferencia_id = token_urlsafe(24)
                self.conferencia_sisplan = dict(id=conferencia_id, entrada=originais, lotes=deepcopy(lotes))
            resultado = dict(lotes=lotes, total=sum(len(lote['ordens']) for lote in lotes),
                             conferencia_id=conferencia_id)
            if por_pedido:
                resultado['pedidos'] = originais
            return resultado

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
                self.dados.update(fase='erro', mensagem=f'Execução interrompida: {erro}')
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
