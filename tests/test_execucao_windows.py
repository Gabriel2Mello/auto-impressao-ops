"""Integração com as funções existentes, substituindo todas as ações de tela."""

import importlib.util
import unittest
from threading import Event
from unittest.mock import Mock, patch

from src.servico_impressao import executar_lotes


@unittest.skipUnless(importlib.util.find_spec('pywinauto'), 'Requer dependências Windows instaladas')
class TestAdaptadorWindows(unittest.TestCase):
    def test_envia_na_ordem_com_setor_e_uma_tentativa(self):
        lotes = [{'setor': '20', 'ordens': ['000001', '000002']},
                 {'setor': '10', 'ordens': ['000003']}]
        atualizar = Mock()
        with patch('src.handle_app.inicia_app', return_value=('app', 'campos')), \
             patch('src.handle_app.preencher_dados_fixos') as preencher, \
             patch('main.processar_ordem') as processar:
            executar_lotes(lotes, Event(), atualizar)
        self.assertEqual([chamada.args for chamada in preencher.call_args_list], [('campos', '20'), ('campos', '10')])
        self.assertEqual([chamada.args[2] for chamada in processar.call_args_list], ['000001', '000002', '000003'])
        self.assertTrue(all(chamada.kwargs == {'max_tentativas': 1} for chamada in processar.call_args_list))
        self.assertEqual(atualizar.call_count, 6)

    def test_parada_durante_op_nao_inicia_proxima(self):
        parar, atualizar = Event(), Mock()
        with patch('src.handle_app.inicia_app', return_value=('app', 'campos')), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.processar_ordem', side_effect=lambda *args, **kwargs: parar.set()) as processar:
            executar_lotes([{'setor': '10', 'ordens': ['000001', '000002']}], parar, atualizar)
        self.assertEqual(processar.call_count, 1)
        self.assertEqual(atualizar.call_args.args, ('enviada', '000001', '10'))

    def test_falha_nao_envia_demais_ordens(self):
        atualizar = Mock()
        with patch('src.handle_app.inicia_app', return_value=('app', 'campos')), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.processar_ordem', side_effect=RuntimeError('Falha sintética')) as processar:
            with self.assertRaises(RuntimeError):
                executar_lotes([{'setor': '10', 'ordens': ['000001', '000002']}], Event(), atualizar)
        self.assertEqual(processar.call_count, 1)
        self.assertEqual(atualizar.call_args.args, ('atual', '000001', '10'))
