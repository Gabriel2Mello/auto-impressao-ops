"""Regressões de envio incerto; todas as ações de tela são simuladas."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch

import main
from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.servico_impressao import EstadoImpressao


class TestConsole(unittest.TestCase):
    def setUp(self):
        contexto = self.enterContext(ExitStack())
        pasta = self.enterContext(TemporaryDirectory())
        contexto.enter_context(patch.dict('os.environ', {
            'NUNES_OPS_DADOS': pasta, 'LOCALAPPDATA': pasta,
            'IMPRESSORA_OP': 'Impressora sintética',
        }))
        self.pasta = Path(pasta)
        self.preferencia = self.pasta / 'Nunes' / 'ImpressaoOPs' / 'config.json'
        self.listar = contexto.enter_context(patch('src.impressoras.listar_impressoras_windows',
            return_value=['Impressora sintética', 'Outra fila']))
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
        self.iniciar_app = contexto.enter_context(patch('main.inicia_app', return_value=(self.app, self.campos)))
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

    def salvar_preferencia(self, nome):
        self.preferencia.parent.mkdir(parents=True, exist_ok=True)
        self.preferencia.write_text(json.dumps({'ultima_impressora': nome}), encoding='utf-8')

    def mensagens(self):
        return '\n'.join(str(chamada.args[0]) for chamada in self.imprimir.call_args_list)

    def test_console_e_web_usam_preferencia_salva_antes_do_ambiente(self):
        self.salvar_preferencia('Impressora sintética')
        os.environ['IMPRESSORA_OP'] = 'Outra fila'
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        nomes_web = []
        def executor(lotes, parar, atualizar, impressora):
            nomes_web.append(impressora)
            atualizar('atual', '000002', '10')
            atualizar('enviada', '000002', '10')
        estado = EstadoImpressao(executor, Impressoras(), DiarioImpressao(self.pasta / 'web.sqlite3'))
        estado.iniciar({'modo': 'lista', 'ordens': '2', 'setor': '10',
                        'impressora': estado.impressoras.selecionada})
        estado.worker.join(3)
        self.assertFalse(estado.worker.is_alive())
        self.assertEqual(main.main(), 0)
        self.combo.select.assert_called_once_with(nomes_web[0])
        self.assertEqual(nomes_web, ['Impressora sintética'])
        self.assertIn('Impressora do lote: Impressora sintética', self.mensagens())
        self.assertEqual(DiarioImpressao().consultar()[0]['impressora'], 'Impressora sintética')

    def test_console_sem_preferencia_usa_ambiente_e_salva_apos_sucesso(self):
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.assertFalse(self.preferencia.exists())
        self.assertEqual(main.main(), 0)
        self.assertEqual(json.loads(self.preferencia.read_text(encoding='utf-8')),
                         {'ultima_impressora': 'Impressora sintética'})
        self.assertEqual(DiarioImpressao().consultar()[0]['impressora'], 'Impressora sintética')

    def test_preferencia_removida_nao_cai_no_ambiente_nem_inicia_sisplan(self):
        self.salvar_preferencia('Fila removida')
        antes = self.preferencia.read_bytes()
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.assertEqual(main.main(), 1)
        self.iniciar_app.assert_not_called()
        self.teclas.assert_not_called()
        self.registrar.assert_not_called()
        self.assertFalse((self.pasta / 'execucoes.sqlite3').exists())
        self.assertEqual(self.preferencia.read_bytes(), antes)
        self.assertIn('Fila removida', self.mensagens())

    def test_sem_preferencia_ou_ambiente_recusa_antes_do_sisplan(self):
        os.environ['IMPRESSORA_OP'] = ''
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.assertEqual(main.main(), 1)
        self.iniciar_app.assert_not_called()
        self.teclas.assert_not_called()
        self.assertFalse(self.preferencia.exists())

    def test_falha_ao_listar_filas_recusa_antes_do_sisplan(self):
        self.listar.side_effect = RuntimeError('Spooler sintético indisponível')
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.assertEqual(main.main(), 1)
        self.iniciar_app.assert_not_called()
        self.assertIn('Spooler sintético indisponível', self.mensagens())

    def test_impressora_fica_fixa_entre_ops_e_setores(self):
        self.obter_lotes.return_value = [
            {'setor': '10', 'ordens': ['000001', '000002']},
            {'setor': '20', 'ordens': ['000003']},
        ]
        def enviar(app, campos, numero, impressora=None):
            self.assertEqual(impressora, 'Impressora sintética')
            os.environ['IMPRESSORA_OP'] = 'Outra fila'
            self.salvar_preferencia('Outra fila')
            return True
        with patch('main.processar_ordem', side_effect=enviar) as enviar_op:
            self.assertEqual(main.main(), 0)
        self.assertEqual(enviar_op.call_count, 3)
        self.assertTrue(all(item['impressora'] == 'Impressora sintética'
                            for item in DiarioImpressao().consultar()))
        # Só o primeiro envio persiste o uso; uma edição posterior fica para o próximo lote.
        self.assertEqual(json.loads(self.preferencia.read_text(encoding='utf-8')),
                         {'ultima_impressora': 'Outra fila'})

    def test_falha_antes_do_primeiro_envio_nao_salva_preferencia(self):
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        self.campos['numero'].set_text.side_effect = RuntimeError('Consulta sintética indisponível')
        self.assertEqual(main.main(), 1)
        self.assertFalse(self.preferencia.exists())
        self.registrar.assert_not_called()

    def test_falha_salvar_preferencia_avisa_e_nao_repete_envio(self):
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001', '000002']}]
        with patch('src.impressoras.os.replace', side_effect=PermissionError('Sem permissão sintética')), \
             self.assertLogs(level='ERROR'):
            self.assertEqual(main.main(), 0)
        self.assertEqual(self.app.window.return_value.OK.click.call_count, 2)
        self.assertEqual(self.registrar.call_count, 2)
        self.assertIn('não foi possível lembrar', self.mensagens())
        self.assertEqual(self.mensagens().count('não foi possível lembrar'), 1)
        self.assertTrue(all(item['situacao'] == 'concluido' for item in DiarioImpressao().consultar()))
        self.assertFalse(self.preferencia.exists())

    def test_configuracao_ilegivel_mantem_aviso_com_ambiente_valido(self):
        self.preferencia.parent.mkdir(parents=True)
        self.preferencia.write_text('{invalido', encoding='utf-8')
        self.obter_lotes.return_value = [{'setor': '10', 'ordens': ['000001']}]
        with self.assertLogs(level='WARNING'):
            self.assertEqual(main.main(), 0)
        self.assertIn('Não foi possível ler a última impressora', self.mensagens())
        self.combo.select.assert_called_once_with('Impressora sintética')


if __name__ == '__main__':
    unittest.main()
