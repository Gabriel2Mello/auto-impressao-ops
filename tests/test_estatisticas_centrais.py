"""Central isolada e fronteiras Windows simuladas; nenhuma impressão real."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import unittest
from unittest.mock import Mock, patch

import impressao
import main
import sincronizar_estatisticas as sync
from contrato_estatisticas import ConfiguracaoCliente, serializar
from metricas_nunes import registrar_evento
from src.diario_impressao import DiarioImpressao
from src.servico_impressao import executar_lotes

RAIZ = Path(__file__).resolve().parents[1]


class TestEstatisticasCentrais(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(self.enterContext(TemporaryDirectory()))
        self.metricas = self.pasta / 'metricas'
        self.arquivo = self.pasta / 'cliente.json'
        self.enterContext(patch.dict(os.environ, {
            'NUNES_METRICAS_DADOS': str(self.metricas),
            'NUNES_OPS_DADOS': str(self.pasta / 'diario'),
            'NUNES_CENTRAL_CONFIG': str(self.arquivo),
        }))
        self.processo = None
        self.addCleanup(self.fechar)
        self.abrir()

    def abrir(self):
        endereco = self.pasta / 'porta.txt'
        endereco.unlink(missing_ok=True)
        script = (
            'import sys;from pathlib import Path;'
            'sys.path.insert(0,sys.argv[1]);from central import Armazem,Servidor;'
            'p=Path(sys.argv[2]);'
            's=Servidor(Armazem(p/"central.sqlite3","c"*32),"token_sintetico_"*3,0);'
            '(p/"porta.tmp").write_text(str(s.server_port));'
            '(p/"porta.tmp").replace(p/"porta.txt");s.serve_forever(poll_interval=.01)'
        )
        self.processo = subprocess.Popen(
            [sys.executable, '-I', '-c', script, str(RAIZ.parent / 'nunes-estatisticas'), str(self.pasta)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        limite = monotonic() + 10
        while True:
            try:
                porta = endereco.read_text()
            except (FileNotFoundError, PermissionError):
                porta = ''  # Publicação/leitura do arquivo temporário pode estar em transição no Windows.
            if porta:
                break
            if self.processo.poll() is not None or monotonic() >= limite:
                self.fail('A central sintética não iniciou.')
            sleep(.02)
        self.config: ConfiguracaoCliente = {
            'protocolo': 1, 'central_id': 'c' * 32, 'token': 'token_sintetico_' * 3,
            'url': 'http://127.0.0.1:' + porta,
        }
        self.arquivo.write_text(serializar(self.config), encoding='utf-8')

    def fechar(self):
        if self.processo is not None:
            if self.processo.poll() is None:
                self.processo.terminate()  # Somente o processo sintético criado neste teste.
            self.processo.communicate(timeout=5)
            self.processo = None

    def cliente(self):
        return sync.Cliente(self.config, self.metricas, aplicacao='impressao-ops')

    def total(self):
        return sync.requisitar(self.config, '/v1/resumo?aplicacao=impressao-ops')['total']

    def produzir(self, setor='10', falha=False):
        lotes = [{'setor': setor, 'ordens': ['000123', '000124']}]
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
                patch('src.handle_app.preencher_dados_fixos'), \
                patch('main.processar_ordem', side_effect=[True, RuntimeError('sintetico')] if falha else None,
                      return_value=True):
            executar_lotes(lotes, Event(), Mock(), 'Fila sintética')

    def test_historico_deduplica_op_setor_e_nao_soma_outros_produtores(self):
        self.produzir(); self.produzir(); self.produzir('20')
        self.assertTrue(registrar_evento('arquivo_transferido', 'arquivo-sintetico', '1234', tipo='busca_pdf'))
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 4)
        self.assertEqual(self.total(), 4)
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 0)
        self.assertEqual(len(sync.Cliente(self.config, self.metricas).pendentes()), 1)

    def test_central_desligada_nao_impede_envio_simulado_e_reinicio_nao_duplica(self):
        self.fechar(); self.produzir()
        with self.assertRaises(OSError):
            self.cliente().sincronizar()
        self.assertEqual(len(self.cliente().pendentes()), 2)
        self.abrir()
        with sync.Sincronizador(aplicacao='impressao-ops', relatar=lambda _: None):
            pass
        self.assertEqual(self.total(), 2)
        self.fechar(); self.abrir()
        self.assertEqual(self.cliente().sincronizar()['pendentes'], 0)
        self.assertEqual(self.total(), 2)

    def test_resposta_perdida_apos_commit_reenvia_sem_imprimir_ou_duplicar(self):
        self.produzir()
        original = sync.requisitar
        def perder(config, caminho, dados=None):
            resposta = original(config, caminho, dados)
            if dados is not None:
                raise OSError('resposta sintética perdida')
            return resposta
        with patch('main.processar_ordem') as imprimir:
            with patch.object(sync, 'requisitar', side_effect=perder), self.assertRaises(OSError):
                self.cliente().sincronizar()
            self.assertEqual(self.total(), 2)
            self.assertEqual(len(self.cliente().pendentes()), 2)
            self.assertEqual(self.cliente().sincronizar()['pendentes'], 0)
            imprimir.assert_not_called()
        self.assertEqual(self.total(), 2)

    def test_fila_e_instante_original_sao_preservados(self):
        with patch('metricas_nunes._abrir', side_effect=sqlite3.OperationalError('sintetico')), self.assertLogs(level='WARNING'):
            self.produzir()
        arquivos = {p: p.read_bytes() for p in (self.metricas / 'recuperar').glob('*.json')}
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 2)
        self.assertEqual({p: p.read_bytes() for p in arquivos}, arquivos)
        esperados = {json.loads(b)['id']: json.loads(b)['ocorrido_em'] for b in arquivos.values()}
        with closing(sqlite3.connect(self.pasta / 'central.sqlite3')) as banco:
            salvos = [json.loads(linha[0]) for linha in banco.execute('SELECT payload FROM eventos')]
        self.assertEqual({r['id']: r['ocorrido_em'] for r in salvos}, esperados)

    def test_web_e_console_sincronizam_sem_depender_do_hub(self):
        servidor = Mock(); servidor.serve_forever.side_effect = self.produzir
        with patch('impressao.logging.basicConfig'), \
                patch('src.interface_web.criar_servidor', return_value=(servidor, Mock())):
            self.assertEqual(impressao.main(Mock()), 0)
        self.assertEqual(self.total(), 2)
        with patch('main.obter_lotes', return_value=[{'setor': '20', 'ordens': ['000123']}]), \
                patch('main.Impressoras') as impressoras, patch('builtins.input', return_value=''), \
                patch('main.inicia_app', return_value=(None, {})), \
                patch('main.preencher_dados_fixos'), patch('main.processar_ordem', return_value=True):
            impressoras.return_value.validar.return_value = 'Fila sintética'
            impressoras.return_value.aviso_preferencia = ''
            self.assertEqual(main.main(), 0)
        self.assertEqual(self.total(), 3)

    def test_falha_no_envio_nao_gera_metrica_para_op_incompleta(self):
        with self.assertRaises(RuntimeError):
            self.produzir(falha=True)
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 1)
        self.assertEqual(self.total(), 1)

    def test_conferencia_manual_do_diario_nao_cria_metrica_central(self):
        diario = DiarioImpressao()
        execucao = diario.iniciar([{'setor': '10', 'ordens': ['000123']}], 'Fila sintética')
        diario.atualizar(execucao, '000123', '10', 'envio_iniciado')
        diario.interromper(execucao)
        diario.conferir(diario.consultar()[0]['id'], 'conferido_enviado')
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 0)
        self.assertEqual(self.total(), 0)

    def test_cliente_individual_sem_repositorios_irmaos(self):
        self.produzir()
        destino = self.pasta / 'individual'; destino.mkdir()
        for nome in ('contrato_estatisticas.py', 'sincronizar_estatisticas.py', 'metricas_nunes.py'):
            shutil.copy2(RAIZ / nome, destino / nome)
        script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                  'import sincronizar_estatisticas as s;'
                  'c=s.ler_configuracao();assert c is not None;'
                  'assert s.Cliente(c,aplicacao="impressao-ops").sincronizar()["pendentes"]==0')
        resultado = subprocess.run([sys.executable, '-I', '-c', script, str(destino)],
                                  cwd=destino, capture_output=True, timeout=10)
        self.assertEqual(resultado.returncode, 0, resultado.stderr.decode(errors='replace'))
        self.assertEqual(self.total(), 2)

    def test_sem_vinculo_nao_cria_worker_nem_requisicao(self):
        with patch.dict(os.environ, {'NUNES_CENTRAL_CONFIG': ''}), \
                patch.object(sync, '__file__', str(self.pasta / 'sincronizar_estatisticas.py')), \
                patch.object(sync, 'requisitar') as pedir:
            with sync.Sincronizador(aplicacao='impressao-ops') as worker:
                self.assertIsNone(worker.worker)
            pedir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
