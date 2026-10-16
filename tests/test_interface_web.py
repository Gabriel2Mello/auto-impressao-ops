import json
import unittest
from http.client import HTTPConnection
from threading import Event, Thread
from unittest.mock import patch

from src.entrada_web import montar_lotes
from src.interface_web import criar_servidor
from src.servico_impressao import ConflitoExecucao, EstadoImpressao


class TestEntrada(unittest.TestCase):
    def test_intervalos_inclusivos_e_op_unica_com_setor_padrao(self):
        lotes = montar_lotes({'modo': 'intervalos', 'intervalos': [
            {'de': '12', 'para': '14', 'setor': '20'}, {'de': '17', 'para': '', 'setor': ''}]})
        self.assertEqual(lotes, [
            {'setor': '20', 'ordens': ['000012', '000013', '000014']},
            {'setor': '10', 'ordens': ['000017']}])

    def test_lista_normaliza_e_elimina_repetidos_como_arquivo(self):
        self.assertEqual(montar_lotes({'modo': 'lista', 'ordens': '12\n000012 13,14;15', 'setor': '10'}),
                         [{'setor': '10', 'ordens': ['000012', '000013', '000014', '000015']}])

    def test_sobreposicao_no_mesmo_setor_sem_remover_outro_setor(self):
        lotes = montar_lotes({'modo': 'intervalos', 'intervalos': [
            {'de': '1', 'para': '2', 'setor': '10'},
            {'de': '2', 'para': '3', 'setor': '10'},
            {'de': '2', 'setor': '20'}]})
        self.assertEqual([lote['ordens'] for lote in lotes], [['000001', '000002'], ['000003'], ['000002']])

    def test_entradas_invalidas_sao_recusadas(self):
        entradas = [None, [], {}, {'modo': 'lista', 'ordens': ''},
                    {'modo': 'lista', 'ordens': '12 inválida'},
                    {'modo': 'lista', 'ordens': '12', 'setor': '%s'},
                    {'modo': 'intervalos', 'intervalos': [{'de': '20', 'para': '10'}]},
                    {'modo': 'intervalos', 'intervalos': [{'de': '1', 'para': '5001'}]},
                    {'modo': 'intervalos', 'intervalos': [{'de': '1', 'para': '3000'}, {'de': '3001', 'para': '6000'}]}]
        for entrada in entradas:
            with self.subTest(entrada=entrada), self.assertRaises(ValueError):
                montar_lotes(entrada)


class TestExecucao(unittest.TestCase):
    entrada = {'modo': 'lista', 'ordens': '1 2 3', 'setor': '10'}

    @patch.dict('os.environ', {'IMPRESSORA_OP': 'Impressora sintética'})
    def test_parada_termina_op_atual_e_recusa_execucao_concorrente(self):
        entrou, liberar = Event(), Event()
        def executor(lotes, parar, atualizar):
            atualizar('atual', '000001', '10')
            entrou.set()
            self.assertTrue(liberar.wait(3))
            atualizar('enviada', '000001', '10')
            self.assertTrue(parar.is_set())
        estado = EstadoImpressao(executor)
        estado.iniciar(self.entrada)
        self.assertTrue(entrou.wait(3))
        try:
            with self.assertRaises(ConflitoExecucao):
                estado.iniciar(self.entrada)
            estado.solicitar_parada()
        finally:
            liberar.set()
            estado.worker.join(3)
        self.assertEqual(estado.situacao()['enviadas'], 1)
        self.assertEqual(estado.situacao()['fase'], 'interrompido')

    @patch.dict('os.environ', {'IMPRESSORA_OP': 'Impressora sintética'})
    def test_falha_nao_repete_op_e_preserva_contagem(self):
        chamadas = []
        def executor(lotes, parar, atualizar):
            chamadas.append(lotes)
            atualizar('atual', '000001', '10')
            atualizar('enviada', '000001', '10')
            atualizar('atual', '000002', '10')
            raise RuntimeError('Falha sintética')
        estado = EstadoImpressao(executor)
        with self.assertLogs(level='ERROR'):
            estado.iniciar(self.entrada)
            estado.worker.join(3)
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(estado.situacao()['fase'], 'erro')
        self.assertEqual(estado.situacao()['enviadas'], 1)
        self.assertEqual(estado.situacao()['atual'], '000002')

    @patch.dict('os.environ', {}, clear=True)
    def test_impressora_ausente_impede_automacao(self):
        estado = EstadoImpressao(lambda *args: self.fail('Não deve acessar Sisplan'))
        with self.assertRaises(RuntimeError):
            estado.iniciar(self.entrada)
        self.assertIsNone(estado.worker)


class TestHttp(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoImpressao(lambda *args: self.fail('Conferência não deve imprimir'))
        self.servidor, _ = criar_servidor(self.estado, porta=0)
        self.thread = Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        self.origem = f'http://127.0.0.1:{self.servidor.server_port}'
        resposta, conteudo = self.requisicao('GET', '/')
        self.assertEqual(resposta.status, 200)
        self.token = conteudo.decode().split('name="impressao-token" content="')[1].split('"')[0]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(3)

    def requisicao(self, metodo, caminho, dados=None, cabecalhos=None):
        conexao = HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            conexao.request(metodo, caminho, body=json.dumps(dados) if dados is not None else None,
                            headers=cabecalhos or {})
            resposta = conexao.getresponse()
            return resposta, resposta.read()
        finally:
            conexao.close()

    def autorizacao(self):
        return {'Authorization': f'Bearer {self.token}', 'Origin': self.origem, 'Content-Type': 'application/json'}

    def test_conferencia_nao_inicia_automacao(self):
        resposta, conteudo = self.requisicao('POST', '/api/conferir', TestExecucao.entrada, self.autorizacao())
        self.assertEqual(resposta.status, 200)
        self.assertEqual(json.loads(conteudo)['total'], 3)
        self.assertIsNone(self.estado.worker)

    def test_bloqueia_token_origem_host_e_caminho_arbitrario(self):
        for cabecalhos in [{}, dict(self.autorizacao(), Origin='https://site-externo.invalid'),
                           dict(self.autorizacao(), Host='externo.invalid')]:
            resposta, _ = self.requisicao('POST', '/api/iniciar', TestExecucao.entrada, cabecalhos)
            self.assertEqual(resposta.status, 403)
        resposta, _ = self.requisicao('GET', '/../../main.py', cabecalhos=self.autorizacao())
        self.assertEqual(resposta.status, 404)

    def test_recursos_visuais_e_validacao_da_api(self):
        for caminho in ['/impressao.css', '/impressao.js', '/icons/icone.svg', '/favicon.ico']:
            resposta, conteudo = self.requisicao('GET', caminho)
            self.assertEqual(resposta.status, 200)
            self.assertTrue(conteudo)
        resposta, _ = self.requisicao('POST', '/api/conferir', {'modo': 'lista', 'ordens': 'erro'}, self.autorizacao())
        self.assertEqual(resposta.status, 400)

    def test_canal_envia_estado_inicial_e_somente_conexao_quando_parado(self):
        conexao = HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            cabecalhos = dict(self.autorizacao(), **{'X-Impressao-Pagina': 'pagina-sintetica'})
            conexao.request('GET', '/api/acompanhar', headers=cabecalhos)
            resposta = conexao.getresponse()
            self.assertEqual(resposta.status, 200)
            self.assertEqual(resposta.getheader('Content-Type'), 'text/event-stream; charset=utf-8')
            self.assertTrue(resposta.readline().startswith(b'data: '))
            self.assertEqual(resposta.readline(), b'\n')
            self.assertEqual(resposta.readline(), b': conexao\n')
            self.assertEqual(resposta.readline(), b'\n')
            self.assertIsNone(self.estado.worker)
            retorno, _ = self.requisicao('POST', '/api/fechar-pagina',
                                        {'pagina': 'pagina-sintetica'}, self.autorizacao())
            self.assertEqual(retorno.status, 200)
            self.assertNotIn('pagina-sintetica', self.servidor.paginas)
        finally:
            conexao.close()


class TestFechamento(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoImpressao()
        self.servidor, _ = criar_servidor(self.estado, porta=0)
        self.addCleanup(self.servidor.server_close)

    def test_sem_primeira_aba_nao_deixa_servidor_abandonado(self):
        with patch('src.interface_web.monotonic', return_value=self.servidor.criado_em + 121), \
                patch('src.interface_web.Thread') as thread:
            self.servidor.service_actions()
            thread.return_value.start.assert_called_once()
        self.assertTrue(self.estado.encerrando)

    def test_fechamento_da_ultima_aba_encerra_apos_tolerancia_de_recarga(self):
        self.servidor.abrir_pagina('aba')
        with patch('src.interface_web.monotonic', return_value=10):
            self.servidor.fechar_pagina('aba')
        with patch('src.interface_web.monotonic', return_value=12):
            self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)
        with patch('src.interface_web.monotonic', return_value=13), patch('src.interface_web.Thread') as thread:
            self.servidor.service_actions()
            thread.return_value.start.assert_called_once()
        self.assertTrue(self.estado.encerrando)
        self.assertTrue(self.estado.parar.is_set())

    def test_recarga_ou_outra_aba_aberta_preserva_programa(self):
        self.servidor.abrir_pagina('antiga')
        self.servidor.fechar_pagina('antiga')
        self.servidor.abrir_pagina('nova')
        self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)
        self.servidor.abrir_pagina('segunda')
        self.servidor.fechar_pagina('nova')
        self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)

    def test_cancelar_saida_mantem_canal_e_nao_pede_parada(self):
        presenca = self.servidor.abrir_pagina('aba')
        for _ in range(3):
            self.servidor.service_actions()
        self.assertFalse(presenca.is_set())
        self.assertFalse(self.estado.encerrando)
        self.assertFalse(self.estado.parar.is_set())

    def test_conexao_antiga_nao_remove_reconexao_da_mesma_pagina(self):
        antiga = self.servidor.abrir_pagina('aba')
        nova = self.servidor.abrir_pagina('aba')
        self.servidor.fechar_pagina('aba', antiga)
        self.assertIs(self.servidor.paginas['aba'], nova)
        self.assertFalse(nova.is_set())


if __name__ == '__main__':
    unittest.main()
