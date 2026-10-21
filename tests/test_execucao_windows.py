"""Integração com as funções existentes, substituindo todas as ações de tela."""

import importlib.util
import unittest
from threading import Event
from unittest.mock import Mock, patch

from src.servico_impressao import executar_lotes


@unittest.skipUnless(importlib.util.find_spec('pywinauto'), 'Requer dependências Windows instaladas')
class TestAdaptadorWindows(unittest.TestCase):
    def test_dialogo_usa_impressora_do_lote_e_confere_nome_antes_de_confirmar(self):
        from src.handle_app import handle_menu_impressao
        app, combo = Mock(), Mock()
        combo.selected_text.return_value = 'Impressora do lote'
        with patch('src.handle_app.get_field_index', return_value=combo), \
             patch('src.handle_app.obter_caminho_impressora', side_effect=AssertionError('Não deve ler a variável')):
            self.assertTrue(handle_menu_impressao(app, impressora='Impressora do lote'))
        combo.select.assert_called_once_with('Impressora do lote')
        app.window.return_value.OK.click.assert_called_once()

    def test_dialogo_nao_confirma_impressora_diferente(self):
        from src.handle_app import handle_menu_impressao
        app, combo = Mock(), Mock()
        combo.selected_text.return_value = 'Outra fila'
        with patch('src.handle_app.get_field_index', return_value=combo), patch('builtins.print'):
            self.assertFalse(handle_menu_impressao(app, impressora='Impressora do lote'))
        app.window.return_value.OK.click.assert_not_called()

    def test_envia_na_ordem_com_setor_e_uma_tentativa(self):
        lotes = [{'setor': '20', 'ordens': ['000001', '000002']},
                 {'setor': '10', 'ordens': ['000003']}]
        atualizar = Mock()
        with patch('src.handle_app.inicia_app', return_value=('app', 'campos')), \
             patch('src.handle_app.preencher_dados_fixos') as preencher, \
             patch('main.processar_ordem') as processar:
            executar_lotes(lotes, Event(), atualizar, impressora='Impressora do lote')
        self.assertEqual([chamada.args for chamada in preencher.call_args_list], [('campos', '20'), ('campos', '10')])
        self.assertEqual([chamada.args[2] for chamada in processar.call_args_list], ['000001', '000002', '000003'])
        self.assertTrue(all(chamada.kwargs == {'impressora': 'Impressora do lote'} for chamada in processar.call_args_list))
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
