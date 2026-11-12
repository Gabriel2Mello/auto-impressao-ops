"""Conferência e preferências do cliente, com consultas sintéticas."""
from datetime import date
import unittest
from unittest.mock import Mock, patch

from src.entrada_web import montar_lotes
from src.protocolo_consulta_ops import ErroConsultaSisplan
from src.servico_impressao import ConflitoExecucao, EstadoImpressao
from src.preferencias_impressao import ler_consulta
from tests.test_interface_web import ComImpressoras


class TestConferencia(ComImpressoras):
    entrada = dict(modo='lista', ordens='1 2', setor='ignorado', consultar_sisplan=True,
                   impressora='Impressora sintética')

    def estado(self):
        self.consultar = Mock(return_value=[dict(faccao='00001', faccao_nome='Fictícia', setor='20',
                                                 setor_nome='Costura', ordens=['000001', '000002'])])
        self.executor = Mock()
        return EstadoImpressao(executor=self.executor, consultar=self.consultar)

    def test_opcao_ignora_setor_manual_e_normaliza_repetidas(self):
        self.assertEqual(montar_lotes(dict(self.entrada, ordens='1 000001 2')),
                         [dict(setor='10', ordens=['000001', '000002'])])
        self.assertEqual(montar_lotes(dict(modo='intervalos', consultar_sisplan=True, intervalos=[
            dict(de='1', para='2', setor='x'), dict(de='2', setor='20')])),
            [dict(setor='10', ordens=['000001', '000002'])])
        with self.assertRaisesRegex(ValueError, 'Opção'):
            montar_lotes(dict(self.entrada, consultar_sisplan='false'))

    def test_desmarcada_preserva_setor_sem_acessar_banco(self):
        estado = self.estado()
        for opcao in ({}, {'consultar_sisplan': False}):
            dados = dict(modo='lista', ordens='1', setor='30', **opcao)
            self.assertEqual(estado.conferir(dados)['lotes'], [dict(setor='30', ordens=['000001'])])
        self.consultar.assert_not_called()

    def test_conferencia_vincula_entrada_e_revalida_antes_de_imprimir(self):
        estado = self.estado()
        resultado = estado.conferir(self.entrada)
        self.executor.assert_not_called()
        self.assertEqual(resultado['total'], 2)
        dados = dict(self.entrada, conferencia_id=resultado['conferencia_id'])
        estado.iniciar(dados)
        estado.worker.join(3)
        self.assertEqual(self.consultar.call_count, 2)
        self.assertEqual(self.executor.call_args.args[0], resultado['lotes'])
        with self.assertRaises(ConflitoExecucao):
            estado.iniciar(dados)

    def test_sem_conferencia_entrada_alterada_ou_outra_aba_bloqueia(self):
        for alterar in ('sem_conferencia', 'entrada', 'outra_aba'):
            with self.subTest(alterar=alterar):
                estado = self.estado()
                resultado = estado.conferir(self.entrada)
                dados = dict(self.entrada, conferencia_id=resultado['conferencia_id'])
                if alterar == 'sem_conferencia':
                    dados.pop('conferencia_id')
                elif alterar == 'entrada':
                    dados['ordens'] = '3'
                else:
                    estado.conferir(self.entrada)
                with self.assertRaises(ConflitoExecucao):
                    estado.iniciar(dados)
                self.executor.assert_not_called()
                self.assertEqual(estado.diario.consultar(), [])

    def test_mudanca_de_localizacao_ou_falha_impede_envio(self):
        for falha in (False, True):
            with self.subTest(falha=falha):
                estado = self.estado()
                resultado = estado.conferir(self.entrada)
                if falha:
                    self.consultar.side_effect = ErroConsultaSisplan('Indisponível')
                else:
                    self.consultar.return_value = [dict(resultado['lotes'][0], setor='30')]
                with self.assertRaises(RuntimeError):
                    estado.iniciar(dict(self.entrada, conferencia_id=resultado['conferencia_id']))
                self.executor.assert_not_called()
                self.assertEqual(estado.diario.consultar(), [])

    def test_pedido_normaliza_ano_e_so_envia_grupo_selecionado(self):
        ano = date.today().year
        lotes = [
            dict(faccao='00261', setor='20', ordens=['000001']),
            dict(faccao='00001', setor='20', ordens=['000002']),
            dict(faccao='00261', setor='30', ordens=['000003']),
        ]
        estado = self.estado()
        estado.buscar_pedidos = Mock(return_value=lotes)
        entrada = dict(modo='pedido', pedidos=f'12345, 2020-54321\r\n{ano}-12345',
                       impressora=self.entrada['impressora'], consultar_sisplan=False)
        resultado = estado.conferir(entrada)
        pedidos = [f'{ano}-12345', '2020-54321']
        self.assertEqual(resultado['pedidos'], pedidos)
        estado.buscar_pedidos.assert_called_once_with(pedidos)
        self.executor.assert_not_called()
        estado.iniciar(dict(entrada, conferencia_id=resultado['conferencia_id'], grupos_selecionados=[1]))
        estado.worker.join(3)
        self.assertEqual(estado.buscar_pedidos.call_count, 2)
        self.assertEqual(self.executor.call_args.args[0], [lotes[1]])
        self.assertEqual([item['numero'] for item in estado.diario.consultar()], ['000002'])
        self.consultar.assert_not_called()

    def test_pedido_recusa_entrada_invalida_selecao_invalida_e_vinculo_alterado(self):
        estado = self.estado()
        lote = dict(faccao='00261', setor='20', ordens=['000001'])
        estado.buscar_pedidos = Mock(return_value=[lote])
        entrada = dict(modo='pedido', pedidos='2025-1234', impressora=self.entrada['impressora'])
        with self.assertRaisesRegex(ValueError, 'Confira estes números'):
            estado.conferir(dict(entrada, pedidos='1234, 25-5678'))
        estado.buscar_pedidos.assert_not_called()
        for selecao in ([], [True], [1], [0, 0]):
            resultado = estado.conferir(entrada)
            with self.assertRaisesRegex(ValueError, 'Selecione pelo menos um grupo válido'):
                estado.iniciar(dict(entrada, conferencia_id=resultado['conferencia_id'], grupos_selecionados=selecao))
        resultado = estado.conferir(entrada)
        estado.buscar_pedidos.return_value = [dict(lote, ordens=['000002'])]
        with self.assertRaisesRegex(ConflitoExecucao, 'mudaram no Sisplan'):
            estado.iniciar(dict(entrada, conferencia_id=resultado['conferencia_id'], grupos_selecionados=[0]))
        self.executor.assert_not_called()
        self.assertEqual(estado.diario.consultar(), [])


class TestPreferenciaConsulta(ComImpressoras):
    def test_salva_marcada_e_desmarcada_antes_de_qualquer_lote_e_restaura(self):
        estado = EstadoImpressao(executor=Mock(), consultar=Mock())
        self.assertFalse(estado.preferencia_consulta())
        for valor in (True, False):
            estado.selecionar_consulta(valor)
            reaberto = EstadoImpressao(executor=Mock(), consultar=Mock())
            self.assertIs(reaberto.preferencia_consulta(), valor)
            self.assertIsNone(reaberto.worker)
            self.assertEqual(reaberto.diario.consultar(), [])
        estado.consultar.assert_not_called()
        estado.executor.assert_not_called()
        self.assertFalse(self.config.exists())  # Não sobrescreve a preferência de impressora.

    def test_valor_invalido_e_falha_de_gravacao_preservam_escolha_anterior(self):
        estado = EstadoImpressao(executor=Mock())
        estado.selecionar_consulta(True)
        for invalido in (None, 'false', 0, 1, []):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                estado.selecionar_consulta(invalido)
        with patch('src.preferencias_impressao.gravar_registro', side_effect=PermissionError('privado')):
            with self.assertRaisesRegex(RuntimeError, 'Não foi possível salvar'):
                estado.selecionar_consulta(False)
        self.assertTrue(estado.preferencia_consulta())
        self.assertTrue(ler_consulta(estado.arquivo_consulta))

    def test_arquivo_invalido_ou_valor_nao_booleano_assume_desmarcada(self):
        estado = EstadoImpressao(executor=Mock())
        for conteudo in ('invalido', '[]', '{"consultar_sisplan":"false"}', '{"consultar_sisplan":1}'):
            estado.arquivo_consulta.write_text(conteudo, encoding='utf-8')
            self.assertFalse(ler_consulta(estado.arquivo_consulta))
