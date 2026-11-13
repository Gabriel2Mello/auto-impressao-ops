"""IIS simulado, executor real em loopback e impressão sintética."""

from hashlib import sha256
from http.client import HTTPConnection
from io import BytesIO
import json
import re
from threading import Event, Thread
from unittest.mock import patch
from pathlib import Path

from integracao_hub import IntegracaoLocal, SisplanOcupado

from portal_ops_cgi import atender
from src.interface_web import criar_servidor
from src.portal_ops import ConfigPortal
from src.servico_impressao import EstadoImpressao
from tests.test_interface_web import ComImpressoras


class TestPortalOps(ComImpressoras):
    origem = 'https://ts01.gratitude.local:8771'
    conta = r'GRATITUDE\operadora'

    def setUp(self):
        super().setUp()
        self.entrou = Event()
        self.liberar = Event()
        self.parou = None

        def imprimir(lotes, parar, atualizar, impressora):
            self.entrou.set()
            self.liberar.wait(3)
            self.parou = parar.is_set()
            atualizar('atual', lotes[0]['ordens'][0], lotes[0]['setor'])
            atualizar('enviada', lotes[0]['ordens'][0], lotes[0]['setor'])

        pasta = Path(self.config).parent / 'hub'
        self.financeiro = self.enterContext(IntegracaoLocal('financeiro', 'Financeiro', True, pasta,
                                                           sisplan_por_operacao=True))
        impressao = self.enterContext(IntegracaoLocal('impressao-ops', 'Impressão', True, pasta,
                                                     sisplan_por_operacao=True))
        self.estado = EstadoImpressao(executor=imprimir, exigir_conferencia=True,
                                     reservar_sisplan=impressao.reservar_sisplan)
        self.servidor, self.config_portal = self.iniciar_executor(self.origem)

    def iniciar_executor(self, origem):
        config = ConfigPortal(origem, 18771, 8772, 'a' * 64)
        servidor, _ = criar_servidor(self.estado, porta=0, portal=config)
        processo = Thread(target=servidor.serve_forever, daemon=True)
        processo.start()

        def fechar():
            self.liberar.set()
            if self.estado.worker:
                self.estado.worker.join(3)
            servidor.shutdown()
            processo.join(3)
            servidor.server_close()

        self.addCleanup(fechar)
        return servidor, ConfigPortal(origem, servidor.server_port, 8772, config.segredo)

    def pedir(self, rota='/', dados=None, token='', conta=None, **ajustes):
        corpo = json.dumps(dados).encode() if dados is not None else b''
        ambiente = dict(HTTPS='on', AUTH_TYPE='Negotiate', LOGON_USER=self.conta if conta is None else conta,
                        HTTP_HOST='ts01.gratitude.local:8771', SCRIPT_NAME=rota,
                        REQUEST_METHOD='GET' if dados is None else 'POST', CONTENT_TYPE='application/json',
                        CONTENT_LENGTH=str(len(corpo)), HTTP_X_IMPRESSAO_TOKEN=token)
        if dados is not None:
            ambiente['HTTP_ORIGIN'] = self.origem
        ambiente.update(ajustes)
        return atender(ambiente, BytesIO(corpo), self.config_portal)

    def abrir(self):
        status, _, corpo = self.pedir()
        self.assertEqual(status, 200)
        self.assertIn(b'name="impressao-portal" content="1"', corpo)
        return re.search(rb'name="impressao-token" content="([^"]+)"', corpo)[1].decode()

    def test_nega_acesso_sem_identidade_https_host_e_origem(self):
        for ajuste in ({'AUTH_TYPE': 'Basic'}, {'LOGON_USER': ''},
                       {'HTTPS': 'off'}, {'HTTP_HOST': 'outro:8771'}):
            self.assertEqual(self.pedir(**ajuste)[0], 403)
        token = self.abrir()
        self.assertEqual(self.pedir('/api/parar', {}, token, HTTP_ORIGIN='https://outra.origem')[0], 403)
        self.assertEqual(self.pedir('/api/parar', {}, token, HTTP_ORIGIN='')[0], 403)
        self.assertEqual(self.pedir('/api/estado', token='')[0], 403)

    def test_publicacao_no_caminho_do_ts01(self):
        _, self.config_portal = self.iniciar_executor('https://ts01')
        host = {'HTTP_HOST': 'ts01'}
        status, cabecalhos, _ = self.pedir('/impressao-ops', **host)
        self.assertEqual((status, cabecalhos), (308, [('Location', '/impressao-ops/')]))
        self.assertEqual(self.pedir('/', **host)[0], 404)
        self.assertEqual(self.pedir('/impressao-ops-falso/', **host)[0], 404)
        status, _, corpo = self.pedir('/impressao-ops/', **host)
        self.assertEqual(status, 200)
        self.assertIn(b'src="impressao.js"', corpo)
        token = re.search(rb'name="impressao-token" content="([^"]+)"', corpo)[1].decode()
        self.assertEqual(self.pedir('/impressao-ops/impressao.js', **host)[0], 200)
        self.assertEqual(self.pedir('/impressao-ops/api/estado', token=token, **host)[0], 200)
        self.assertEqual(self.pedir('/impressao-ops/api/parar', {}, token,
                                    HTTP_ORIGIN='https://outra.origem', **host)[0], 403)
        self.assertEqual(self.pedir('/impressao-ops/api/conferir',
                                    {'modo': 'lista', 'ordens': '1', 'setor': '10',
                                     'impressora': self.nomes[0]}, token,
                                    HTTP_ORIGIN='https://ts01', **host)[0], 200)

    def test_bloqueia_acesso_direto_e_rotas_de_controle_local(self):
        conexao = HTTPConnection('127.0.0.1', self.servidor.server_port)
        try:
            conexao.request('GET', '/', headers={
                'X-Impressao-Portal': 'b' * 64,
                'X-Impressao-Operador': sha256(self.conta.encode()).hexdigest(),
            })
            self.assertEqual(conexao.getresponse().status, 403)
        finally:
            conexao.close()
        token = self.abrir()
        for rota in ('/api/encerrar', '/api/fechar-pagina', '/nunes/encerrar', '/desktop/ativar'):
            self.assertEqual(self.pedir(rota, {}, token)[0], 404)

    def test_conta_e_token_isolados_e_expiram_sem_atividade(self):
        token = self.abrir()
        outra = r'GRATITUDE\outra'
        self.assertEqual(self.pedir(conta=outra)[0], 409)
        self.assertEqual(self.pedir('/api/estado', token=token, conta=outra)[0], 403)
        from time import monotonic
        with patch('src.interface_web.monotonic', return_value=monotonic() + 121):
            self.assertEqual(self.pedir('/api/estado', token=token)[0], 403)
            self.assertNotEqual(self.abrir(), token)

    def test_conferencia_obrigatoria_e_lote_continua_sem_navegador(self):
        token = self.abrir()
        dados = dict(modo='lista', ordens='1', setor='10', impressora=self.nomes[0])
        self.assertEqual(self.pedir('/api/iniciar', dados, token)[0], 409)
        self.assertFalse(self.entrou.is_set())
        status, _, corpo = self.pedir('/api/conferir', dados, token)
        self.assertEqual(status, 200)
        conferencia = json.loads(corpo)['conferencia_id']
        self.assertEqual(self.pedir('/api/iniciar', dict(dados, conferencia_id=conferencia), token)[0], 200)
        self.assertTrue(self.entrou.wait(1))
        self.assertEqual(self.pedir(conta=r'GRATITUDE\outra')[0], 409)
        self.servidor.service_actions()
        self.assertFalse(self.servidor.fechando)
        self.liberar.set()
        self.estado.worker.join(3)
        self.assertFalse(self.parou)
        self.assertEqual(self.estado.situacao()['fase'], 'concluido')

    def test_reserva_recusada_preserva_conferencia_sem_criar_lote(self):
        token = self.abrir()
        dados = dict(modo='lista', ordens='1', setor='10', impressora=self.nomes[0])
        _, _, corpo = self.pedir('/api/conferir', dados, token)
        dados['conferencia_id'] = json.loads(corpo)['conferencia_id']
        reserva = self.financeiro.reservar_sisplan()
        try:
            status, _, corpo = self.pedir('/api/iniciar', dados, token)
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(corpo)['codigo'], 'sisplan_ocupado')
            self.assertEqual(self.estado.diario.consultar(), [])
        finally:
            reserva.fechar()
        self.assertEqual(self.pedir('/api/iniciar', dados, token)[0], 200)
        self.assertTrue(self.entrou.wait(1))
        with self.assertRaises(SisplanOcupado):
            self.financeiro.reservar_sisplan()
        self.assertEqual(self.pedir('/api/parar', {}, token)[0], 200)
        with self.assertRaises(SisplanOcupado):
            self.financeiro.reservar_sisplan()
        self.liberar.set()
        self.estado.worker.join(3)
        self.assertTrue(self.parou)
        self.financeiro.reservar_sisplan().fechar()
