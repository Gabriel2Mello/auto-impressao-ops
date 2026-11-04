"""Banco sintético em memória; nenhum acesso ao Sisplan ou à impressora."""
import sqlite3
import unittest
from unittest.mock import Mock, patch

from src.consulta_sisplan import ErroConsultaSisplan, conectar_configurado, consultar_localizacoes
from src.entrada_web import montar_lotes
from tests.test_interface_web import ComImpressoras
from src.servico_impressao import ConflitoExecucao, EstadoImpressao
from src.preferencias_impressao import ler_consulta


class TestConsulta(unittest.TestCase):
    def setUp(self):
        self.banco = sqlite3.connect(':memory:')
        self.addCleanup(self.banco.close)
        self.banco.execute("ATTACH DATABASE ':memory:' AS sisplan")
        self.banco.executescript('''CREATE TABLE sisplan.faccao_001
            (numero TEXT, codcli TEXT, op TEXT, qt_orig INTEGER, quant INTEGER,
             quant_2 INTEGER, quant_i INTEGER, quant_f INTEGER);
            CREATE TABLE sisplan.entidade_001(codcli TEXT, nome TEXT);
            CREATE TABLE sisplan.cadfluxo_001(codigo TEXT, descricao TEXT);
            INSERT INTO sisplan.entidade_001 VALUES ('00001','Facção fictícia');
            INSERT INTO sisplan.cadfluxo_001 VALUES ('20','Costura fictícia');''')
        self.cursor = Mock()
        self.conexao = Mock()
        self.conexao.cursor.return_value = self.cursor

        def executar(sql, parametros=()):
            if sql.startswith('SET '):
                return
            self.resultado = self.banco.execute(sql.replace('%s', '?'), parametros).fetchall()
        self.cursor.execute.side_effect = executar
        self.cursor.fetchall.side_effect = lambda: self.resultado
        self.lotes = [dict(setor='10', ordens=['000001', '000002'])]

    def inserir(self, numero='000001', faccao='00001', setor='20', original=10,
                quant=0, segunda=0, incompleto=0, perdido=0):
        self.banco.execute('INSERT INTO sisplan.faccao_001 VALUES (?,?,?,?,?,?,?,?)',
                           (numero, faccao, setor, original, quant, segunda, incompleto, perdido))

    def consultar(self, lotes=None):
        return consultar_localizacoes(lotes or self.lotes, conectar=lambda: self.conexao)

    def test_saldo_por_linha_agrupa_e_ignora_etapas_baixadas(self):
        self.inserir(quant=5)
        self.inserir(quant=5)  # Outra cor/tamanho: não duplica impressão.
        self.inserir(faccao='00002', setor='10', original=10, quant=3, segunda=2, incompleto=1, perdido=4)
        self.inserir(numero='000002', faccao='00002', setor='30')
        resultado = self.consultar()
        self.assertEqual(resultado, [dict(faccao='00001', faccao_nome='Facção fictícia', setor='20',
                                          setor_nome='Costura fictícia', ordens=['000001']),
                                    dict(faccao='00002', faccao_nome='', setor='30', setor_nome='', ordens=['000002'])])
        self.assertEqual(self.cursor.execute.call_args_list[0].args[0],
                         'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('000001', '000002'))
        self.conexao.rollback.assert_called_once()
        self.cursor.close.assert_called_once()
        self.conexao.close.assert_called_once()

    def test_nulos_movimentados_e_mesmo_grupo(self):
        self.inserir(quant=None, segunda=None, incompleto=None, perdido=None)
        self.inserir(numero='000002')
        self.assertEqual(self.consultar()[0]['ordens'], ['000001', '000002'])

    def test_ignora_etiquetas_na_mesma_faccao_ou_em_outra(self):
        self.inserir(numero='037442', faccao='00261', setor='10')
        self.inserir(numero='037442', faccao='00261', setor='11')
        self.inserir(numero='037442', faccao='00002', setor='11')
        self.inserir(numero='037442', faccao=None, setor=' 11 ')
        self.assertEqual(self.consultar([dict(setor='10', ordens=['037442'])]),
                         [dict(faccao='00261', faccao_nome='', setor='10',
                               setor_nome='', ordens=['037442'])])

    def test_somente_etiquetas_nao_define_localizacao(self):
        self.inserir(setor='11')
        with self.assertRaisesRegex(ErroConsultaSisplan, 'OP 000001: não encontrada'):
            self.consultar([dict(setor='10', ordens=['000001'])])

    def test_etiquetas_nao_ocultam_ambiguidade_entre_localizacoes_produtivas(self):
        self.inserir(setor='10')
        self.inserir(setor='20')
        self.inserir(setor='11')
        with self.assertRaisesRegex(ErroConsultaSisplan, 'mais de uma localização') as erro:
            self.consultar([dict(setor='10', ordens=['000001'])])
        self.assertIn('setor 10', str(erro.exception))
        self.assertIn('setor 20', str(erro.exception))
        self.assertNotIn('setor 11', str(erro.exception))

    def test_ausente_sem_saldo_e_localizacao_ambigua_bloqueiam(self):
        for configurar, mensagem in [
            (lambda: None, 'não encontrada'),
            (lambda: self.inserir(quant=10), 'não encontrada'),
            (lambda: (self.inserir(), self.inserir(setor='30')), 'mais de uma localização'),
            (lambda: (self.inserir(), self.inserir(faccao='00002')), 'mais de uma localização'),
            (lambda: self.inserir(faccao=None), 'inválido')]:
            with self.subTest(mensagem=mensagem):
                self.banco.execute('DELETE FROM sisplan.faccao_001')
                configurar()
                with self.assertRaisesRegex(ErroConsultaSisplan, mensagem):
                    self.consultar([dict(setor='10', ordens=['000001'])])

    def test_falha_na_consulta_fecha_conexao_sem_expor_segredos(self):
        self.cursor.execute.side_effect = RuntimeError('senha secreta')
        with self.assertRaises(ErroConsultaSisplan) as erro:
            self.consultar()
        self.assertNotIn('secreta', str(erro.exception))
        self.conexao.rollback.assert_called_once()
        self.conexao.close.assert_called_once()

    def test_falha_na_configuracao_nao_expoe_conteudo(self):
        with patch('src.consulta_sisplan.Path.read_text', side_effect=RuntimeError('senha secreta')):
            with self.assertRaisesRegex(ErroConsultaSisplan, '^Banco Sisplan indisponível'):
                conectar_configurado()

    def test_falha_no_fechamento_bloqueia_resultado(self):
        self.inserir()
        self.conexao.rollback.side_effect = RuntimeError('erro privado')
        with self.assertRaisesRegex(ErroConsultaSisplan, 'encerrar a leitura'):
            self.consultar([dict(setor='10', ordens=['000001'])])
        self.cursor.close.assert_called_once()
        self.conexao.close.assert_called_once()


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
