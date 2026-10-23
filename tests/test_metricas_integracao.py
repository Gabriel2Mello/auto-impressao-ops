import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

import main
from metricas_nunes import consultar_metricas, registrar_evento
from src.servico_impressao import executar_lotes
from src.diario_impressao import DiarioImpressao


class TestMetricasIntegracao(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ambiente = patch.dict(os.environ, {'NUNES_METRICAS_DADOS': self.temp.name, 'NUNES_OPS_DADOS': self.temp.name})
        ambiente.start(); self.addCleanup(ambiente.stop)
        self.lotes = [{'setor': '10', 'ordens': ['000001', '000002']}]

    def total(self):
        return consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})['totais']['op_enviada']

    def executar_web(self, lotes):
        diario = DiarioImpressao()
        execucao = diario.iniciar(lotes, 'Impressora sintética')
        def atualizar(evento, numero, setor):
            diario.atualizar(execucao, numero, setor, 'concluido' if evento == 'enviada' else 'envio_iniciado')
        executar_lotes(lotes, Event(), atualizar, 'Impressora sintética')

    def test_web_conta_concluidas_e_nao_conta_op_com_falha(self):
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.processar_ordem', side_effect=[True, RuntimeError('sintetico')]):
            with self.assertRaises(RuntimeError):
                self.executar_web(self.lotes)
        self.assertEqual(self.total(), 1)

    def test_web_e_console_contam_novos_envios_e_reimpressao_independe_do_setor(self):
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.preencher_dados_fixos'), patch('main.processar_ordem', return_value=True):
            self.executar_web(self.lotes)
            main.processar_lote(None, {}, self.lotes[0], impressora='Impressora sintética')
            self.assertEqual(self.total(), 4)
            main.processar_lote(None, {}, {'setor': '20', 'ordens': ['000001']},
                                impressora='Impressora sintética')
            self.assertEqual(self.total(), 5)
            totais = consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})['totais']
            self.assertEqual(totais['ops_repetidas'], 3)
            DiarioImpressao().publicar_metricas()
            self.assertEqual(self.total(), 5)

    def test_parada_antes_de_iniciar_nao_registra(self):
        parar = Event(); parar.set()
        executar_lotes(self.lotes, parar, Mock())
        self.assertEqual(self.total(), 0)

    def test_primeira_impressao_nova_soma_ao_contador_legado_e_conta_reimpressao(self):
        registrar_evento('op_enviada', '000001:10', '000001', empresa='FILIAL', setor='10')
        with patch('main.preencher_dados_fixos'), patch('main.processar_ordem', return_value=True):
            main.processar_lote(None, {}, {'setor': '10', 'ordens': ['000001']},
                                impressora='Impressora sintética')
        dados = consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})
        self.assertEqual(dados['totais']['op_enviada'], 2)
        self.assertEqual(dados['totais']['ops_repetidas'], 1)
