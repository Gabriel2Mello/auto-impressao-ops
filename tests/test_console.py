"""Regressões de envio incerto; todas as ações de tela são simuladas."""

from contextlib import ExitStack
import unittest
from unittest.mock import Mock, call, patch

import main


class TestConsole(unittest.TestCase):
    def setUp(self):
        contexto = self.enterContext(ExitStack())
        self.app = Mock()
        self.campos = {'numero': Mock()}
        self.combo = Mock()
        self.combo.selected_text.return_value = 'Impressora sintética'
        contexto.enter_context(patch('src.handle_app.get_field_index', return_value=self.combo))
        contexto.enter_context(patch('src.handle_app.obter_caminho_impressora', return_value='Impressora sintética'))
        contexto.enter_context(patch('main.sleep'))
        self.teclas = contexto.enter_context(patch('main.send_keys'))
        self.aguardar = contexto.enter_context(patch('main.aguardar', return_value=self.campos['numero']))
        self.mini_menu = contexto.enter_context(patch('main.handle_mini_menu', return_value=True))
        self.fechar_menu = contexto.enter_context(patch('main.fecha_menu_impressao'))
        self.preencher = contexto.enter_context(patch('main.preencher_dados_fixos'))
        self.registrar = contexto.enter_context(patch('main.registrar_evento'))
        self.obter_lotes = contexto.enter_context(patch('main.obter_lotes'))
        contexto.enter_context(patch('main.inicia_app', return_value=(self.app, self.campos)))
        contexto.enter_context(patch('builtins.input', return_value=''))
        self.imprimir = contexto.enter_context(patch('builtins.print'))

    def test_sucesso_mantem_sequencia_e_confirma_uma_vez(self):
        self.assertTrue(main.processar_ordem(self.app, self.campos, '000123'))
        self.campos['numero'].set_text.assert_called_once_with('000123')
        self.assertEqual(self.teclas.call_args_list, [
            call(main.ATALHOS['consultar']), call(main.ATALHOS['imprimir'])])
        self.combo.select.assert_called_once_with('Impressora sintética')
        self.app.window.return_value.OK.click.assert_called_once()
        self.fechar_menu.assert_not_called()

    def test_falha_na_consulta_interrompe_sem_tentar_imprimir(self):
        falha = RuntimeError('Consulta sintética indisponível')
        self.campos['numero'].set_text.side_effect = falha
        with self.assertRaises(RuntimeError) as captura:
            main.processar_ordem(self.app, self.campos, '000123')
        self.assertIs(captura.exception.__cause__, falha)
        self.assertIn('000123', str(captura.exception))
        self.campos['numero'].set_text.assert_called_once()
        self.teclas.assert_not_called()
        self.app.window.return_value.OK.click.assert_not_called()

    def test_falha_antes_do_clique_nao_repete_e_orienta_conferencia(self):
        self.combo.selected_text.return_value = 'Outra fila'
        with self.assertRaises(RuntimeError) as captura:
            main.processar_ordem(self.app, self.campos, '000123')
        self.combo.select.assert_called_once()
        self.app.window.return_value.OK.click.assert_not_called()
        self.fechar_menu.assert_called_once_with(self.app)
        self.assertIn('Confira a OP 000123', str(captura.exception))

    def test_falha_apos_clique_nao_repete_envio_incerto(self):
        # A espera falha após enviar; uma repetição teria sucesso e duplicaria o envio.
        self.app.window.return_value.wait_not.side_effect = [TimeoutError('Envio incerto'), None]
        with self.assertRaises(RuntimeError) as captura:
            main.processar_ordem(self.app, self.campos, '000123')
        self.app.window.return_value.OK.click.assert_called_once()
        self.campos['numero'].set_text.assert_called_once()
        self.fechar_menu.assert_called_once_with(self.app)
        self.assertIn('sem repetição automática', str(captura.exception))
        self.assertIn('Confira a OP 000123', str(captura.exception))

    def test_console_para_ordens_e_setores_e_conta_apenas_sucesso(self):
        self.obter_lotes.return_value = [
            {'setor': '10', 'ordens': ['000001', '000002', '000003']},
            {'setor': '20', 'ordens': ['000004']},
        ]
        self.app.window.return_value.wait_not.side_effect = [None, TimeoutError('Envio incerto'), None]
        self.assertEqual(main.main(), 1)
        self.assertEqual(self.app.window.return_value.OK.click.call_count, 2)
        self.assertEqual(self.campos['numero'].set_text.call_args_list, [call('000001'), call('000002')])
        self.preencher.assert_called_once_with(self.campos, '10')
        self.registrar.assert_called_once_with(
            'op_enviada', '000001:10', '000001', empresa='FILIAL', setor='10')
        mensagens = '\n'.join(str(chamada.args[0]) for chamada in self.imprimir.call_args_list)
        self.assertIn('Confira a OP 000002', mensagens)
        self.assertIn('fila da impressora e no papel', mensagens)

    def test_console_concluido_retorna_sucesso(self):
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.assertEqual(main.main(), 0)
        self.app.window.return_value.OK.click.assert_called_once()
        self.registrar.assert_called_once()


if __name__ == '__main__':
    unittest.main()
