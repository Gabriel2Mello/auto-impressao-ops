import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

import main
from metricas_nunes import consultar_metricas
from src.servico_impressao import executar_lotes


class TestMetricasIntegracao(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ambiente = patch.dict(os.environ, {'NUNES_METRICAS_DADOS': self.temp.name, 'NUNES_OPS_DADOS': self.temp.name})
        ambiente.start(); self.addCleanup(ambiente.stop)
        self.lotes = [{'setor': '10', 'ordens': ['000001', '000002']}]

    def total(self):
        return consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})['totais']['op_enviada']

    def test_web_conta_concluidas_e_nao_conta_op_com_falha(self):
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.processar_ordem', side_effect=[True, RuntimeError('sintetico')]):
            with self.assertRaises(RuntimeError):
                executar_lotes(self.lotes, Event(), Mock(), 'Impressora sintética')
        self.assertEqual(self.total(), 1)

    def test_web_e_console_nao_contam_reenvio_do_mesmo_setor(self):
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.preencher_dados_fixos'), patch('main.processar_ordem', return_value=True):
            executar_lotes(self.lotes, Event(), Mock(), 'Impressora sintética')
            main.processar_lote(None, {}, self.lotes[0])
            self.assertEqual(self.total(), 2)
            main.processar_lote(None, {}, {'setor': '20', 'ordens': ['000001']})
            self.assertEqual(self.total(), 3)

    def test_parada_antes_de_iniciar_nao_registra(self):
        parar = Event(); parar.set()
        executar_lotes(self.lotes, parar, Mock())
        self.assertEqual(self.total(), 0)
