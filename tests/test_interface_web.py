import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from http.client import HTTPConnection
from threading import Event, Thread
from unittest.mock import patch

from src.entrada_web import montar_lotes
from src.diario_impressao import DiarioImpressao
from src.interface_web import criar_servidor
from src.impressoras import Impressoras
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


class ComImpressoras(unittest.TestCase):
    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(patch.dict('os.environ', {'NUNES_OPS_DADOS': pasta.name}))
        self.enterContext(patch('src.servico_impressao.DiarioImpressao', side_effect=lambda: DiarioImpressao(Path(pasta.name) / 'execucoes.sqlite3')))
        self.config = Path(pasta.name) / 'config.json'
        self.nomes = ['Impressora sintética', 'Outra impressora']
        fabrica = patch('src.servico_impressao.Impressoras', side_effect=lambda: Impressoras(
            self.config, listar=lambda: list(self.nomes)))
        fabrica.start()
        self.addCleanup(fabrica.stop)
        ambiente = patch.dict('os.environ', {'IMPRESSORA_OP': 'Impressora sintética'})
        ambiente.start()
        self.addCleanup(ambiente.stop)


class TestExecucao(ComImpressoras):
    entrada = {'modo': 'lista', 'ordens': '1 2 3', 'setor': '10', 'impressora': 'Impressora sintética'}

    @patch.dict('os.environ', {'IMPRESSORA_OP': 'Impressora sintética'})
    def test_parada_termina_op_atual_e_recusa_execucao_concorrente(self):
        entrou, liberar = Event(), Event()
        def executor(lotes, parar, atualizar, impressora):
            self.assertEqual(impressora, 'Impressora sintética')
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
            with self.assertRaises(ConflitoExecucao):
                estado.selecionar_impressora('Outra impressora')
            estado.solicitar_parada()
        finally:
            liberar.set()
            estado.worker.join(3)
        self.assertEqual(estado.situacao()['enviadas'], 1)
        self.assertEqual(estado.situacao()['fase'], 'interrompido')

    @patch.dict('os.environ', {'IMPRESSORA_OP': 'Impressora sintética'})
    def test_falha_nao_repete_op_e_preserva_contagem(self):
        chamadas = []
        def executor(lotes, parar, atualizar, impressora):
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
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')),
                         {'ultima_impressora': 'Impressora sintética'})

    @patch.dict('os.environ', {}, clear=True)
    def test_impressora_ausente_impede_automacao(self):
        estado = EstadoImpressao(lambda *args: self.fail('Não deve acessar Sisplan'))
        with self.assertRaises(RuntimeError):
            estado.iniciar(self.entrada)
        self.assertIsNone(estado.worker)

    def test_fila_removida_impede_execucao(self):
        estado = EstadoImpressao(lambda *args: self.fail('Não deve acessar Sisplan'))
        self.nomes.clear()
        with self.assertRaisesRegex(RuntimeError, 'não está instalada'):
            estado.iniciar(self.entrada)
        self.assertEqual(estado.situacao()['impressora'], '')
        self.assertIsNone(estado.worker)

    def test_outra_aba_altera_impressora_sem_iniciar_lote_antigo(self):
        estado = EstadoImpressao(lambda *args: self.fail('Não deve acessar Sisplan'))
        estado.selecionar_impressora('Outra impressora')
        with self.assertRaisesRegex(ConflitoExecucao, 'outra aba'):
            estado.iniciar(self.entrada)
        self.assertFalse(self.config.exists())

    def test_falha_antes_do_primeiro_envio_preserva_preferencia(self):
        self.config.write_text(json.dumps({'ultima_impressora': 'Outra impressora'}), encoding='utf-8')
        def executor(*args):
            raise RuntimeError('Falha antes de enviar')
        estado = EstadoImpressao(executor)
        estado.selecionar_impressora('Impressora sintética')
        with self.assertLogs(level='ERROR'):
            estado.iniciar(self.entrada)
            estado.worker.join(3)
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8'))['ultima_impressora'], 'Outra impressora')

    def test_falha_ao_salvar_nao_interrompe_lote(self):
        def executor(lotes, parar, atualizar, impressora):
            for numero in lotes[0]['ordens']:
                atualizar('atual', numero, '10')
                atualizar('enviada', numero, '10')
        estado = EstadoImpressao(executor)
        with patch('src.impressoras.os.replace', side_effect=PermissionError('sem permissão')), self.assertLogs(level='ERROR'):
            estado.iniciar(self.entrada)
            estado.worker.join(3)
        self.assertEqual(estado.situacao()['fase'], 'concluido')
        self.assertEqual(estado.situacao()['enviadas'], 3)
        self.assertIn('não foi possível lembrar', estado.situacao()['aviso_impressora'])


class TestHttp(ComImpressoras):
    def setUp(self):
        super().setUp()
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

    def test_recuperacao_exige_autorizacao_e_conferencia_e_nao_imprime(self):
        execucao = self.estado.diario.iniciar([{'setor': '10', 'ordens': ['000001']}])
        self.estado.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        item = self.estado.diario.consultar()[0]
        dados = {'id': item['id'], 'resultado': 'conferido_nao_enviado'}
        resposta, _ = self.requisicao('POST', '/api/conferir-impressao', dados)
        self.assertEqual(resposta.status, 403)
        resposta, _ = self.requisicao('POST', '/api/conferir-impressao', dados, self.autorizacao())
        self.assertEqual(resposta.status, 400)
        resposta, conteudo = self.requisicao('POST', '/api/conferir-impressao',
                                            dict(dados, conferi_fila_e_papel=True), self.autorizacao())
        self.assertEqual(resposta.status, 200)
        self.assertEqual(json.loads(conteudo)['historico'][0]['situacao'], 'conferido_nao_enviado')
        self.assertIsNone(self.estado.worker)

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

    def test_listar_selecionar_e_validar_impressoras_exige_autorizacao(self):
        for metodo, caminho, dados in [('GET', '/api/impressoras', None),
                                        ('POST', '/api/impressora', {'impressora': 'Outra impressora'})]:
            resposta, _ = self.requisicao(metodo, caminho, dados)
            self.assertEqual(resposta.status, 403)
        resposta, conteudo = self.requisicao('GET', '/api/impressoras', cabecalhos=self.autorizacao())
        self.assertEqual(resposta.status, 200)
        self.assertEqual(json.loads(conteudo)['impressoras'], self.nomes)
        resposta, conteudo = self.requisicao('POST', '/api/impressora', {'impressora': 'Outra impressora'}, self.autorizacao())
        self.assertEqual(resposta.status, 200)
        self.assertEqual(json.loads(conteudo)['impressora'], 'Outra impressora')
        self.assertFalse(self.config.exists())
        resposta, _ = self.requisicao('POST', '/api/impressora', {'impressora': 'Não instalada'}, self.autorizacao())
        self.assertEqual(resposta.status, 400)
        self.assertEqual(self.estado.situacao()['impressora'], 'Outra impressora')

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


class TestFechamento(ComImpressoras):
    def setUp(self):
        super().setUp()
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
