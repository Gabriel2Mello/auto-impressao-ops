import http.client
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from demonstracao import EstadoDemonstracao
from src.interface_web import criar_servidor


class TestDemonstracao(unittest.TestCase):
    def test_execucao_e_falha_usam_somente_dados_ficticios(self):
        with TemporaryDirectory() as pasta, \
                patch('src.impressoras.listar_impressoras_windows', side_effect=AssertionError('Fila real')), \
                patch('src.diario_impressao.registrar_evento', side_effect=AssertionError('Métrica real')):
            estado = EstadoDemonstracao(pasta, atraso=0)
            dados = dict(modo='lista', ordens='1 2', setor='10', impressora=estado.impressoras.selecionada)
            estado.iniciar(dados)
            estado.worker.join(3)
            self.assertFalse(estado.worker.is_alive())
            self.assertEqual(estado.situacao()['enviadas'], 2)
            estado.configurar_demo({'resultado': 'erro'})
            with self.assertLogs(level='ERROR'):
                estado.iniciar(dados)
                estado.worker.join(3)
            situacao = estado.situacao()
            self.assertEqual(situacao['fase'], 'erro')
            self.assertTrue(any(item['situacao'] == 'incerto' for item in situacao['historico']))
            self.assertEqual(estado.diario.caminho.parent, Path(pasta))
            with self.assertRaises(ValueError):
                estado.configurar_demo({'resultado': 'invalido'})

    def test_controles_e_rota_exigem_modo_demo_e_autenticacao(self):
        with TemporaryDirectory() as pasta:
            servidor, _ = criar_servidor(EstadoDemonstracao(pasta, atraso=0), porta=0)
            thread = Thread(target=servidor.serve_forever)
            thread.start()
            try:
                def pedido(metodo, rota, token=None):
                    conexao = http.client.HTTPConnection('127.0.0.1', servidor.server_port)
                    headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{servidor.server_port}'}
                    if token:
                        headers['Authorization'] = 'Bearer ' + token
                    conexao.request(metodo, rota, body=json.dumps({'resultado': 'erro'}) if metodo == 'POST' else None, headers=headers)
                    resposta = conexao.getresponse()
                    status, corpo = resposta.status, resposta.read().decode()
                    conexao.close()
                    return status, corpo
                _, pagina = pedido('GET', '/')
                token = re.search('name="impressao-token" content="([^"]+)"', pagina)[1]
                self.assertNotIn('id="demo-resultado"', pagina)
                self.assertEqual(pedido('POST', '/api/demonstracao', token)[0], 404)
                servidor.demonstracao = True
                self.assertIn('id="demo-resultado"', pedido('GET', '/')[1])
                self.assertEqual(pedido('POST', '/api/demonstracao')[0], 403)
                self.assertEqual(pedido('POST', '/api/demonstracao', token)[0], 200)
            finally:
                servidor.shutdown()
                thread.join(3)
                servidor.server_close()
