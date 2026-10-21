from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.servico_impressao import EstadoImpressao


class TestDiario(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(TemporaryDirectory())
        self.caminho = Path(pasta) / 'execucoes.sqlite3'
        self.lotes = [{'setor': '10', 'ordens': ['000001', '000002', '000003']}]
        self.diario = DiarioImpressao(self.caminho)
        self.impressoras = Impressoras(Path(pasta) / 'config.json', listar=lambda: ['Fila sintética'])
        self.impressoras.selecionar('Fila sintética')

    def test_reabertura_preserva_concluido_incerto_e_nao_iniciado(self):
        execucao = self.diario.iniciar(self.lotes, 'Fila sintética')
        self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        self.diario.atualizar(execucao, '1', '10', 'concluido')
        self.diario.atualizar(execucao, '2', '10', 'envio_iniciado')
        reaberto = DiarioImpressao(self.caminho)
        self.assertEqual([i['situacao'] for i in reaberto.consultar()], ['concluido', 'envio_iniciado', 'pendente'])
        with self.assertRaisesRegex(RuntimeError, 'incerta'):
            reaberto.iniciar([{'setor': '20', 'ordens': ['000004']}])
        reaberto.interromper(execucao)
        incerto = reaberto.consultar()[1]
        reaberto.conferir(incerto['id'], 'conferido_nao_enviado')
        with self.assertRaises(ValueError):
            reaberto.conferir(incerto['id'], 'conferido_enviado')
        self.assertEqual(reaberto.consultar()[1]['situacao'], 'conferido_nao_enviado')
        reaberto.iniciar([{'setor': '10', 'ordens': ['000002']}])

    def test_falha_apos_envio_nao_repete_ao_reabrir_servico(self):
        chamadas = []
        def executor(lotes, parar, atualizar, impressora):
            chamadas.append('envio')
            atualizar('atual', '000001', '10')
            raise TimeoutError('Falha após clique simulado')
        estado = EstadoImpressao(executor, self.impressoras, self.diario)
        with self.assertLogs(level='ERROR'):
            estado.iniciar({'modo': 'lista', 'ordens': '1 2 3', 'setor': '10', 'impressora': 'Fila sintética'})
            estado.worker.join(3)
        self.assertEqual([i['situacao'] for i in self.diario.consultar()], ['incerto', 'pendente', 'pendente'])
        reaberto = EstadoImpressao(executor, self.impressoras, DiarioImpressao(self.caminho))
        with self.assertRaisesRegex(RuntimeError, 'incerta'):
            reaberto.iniciar({'modo': 'lista', 'ordens': '4', 'impressora': 'Fila sintética'})
        self.assertEqual(chamadas, ['envio'])
        item = reaberto.situacao()['historico'][0]
        with self.assertRaises(ValueError):
            reaberto.conferir_impressao({'id': item['id'], 'resultado': 'conferido_enviado'})
        reaberto.conferir_impressao({'id': item['id'], 'resultado': 'conferido_enviado', 'conferi_fila_e_papel': True})
        self.assertEqual(chamadas, ['envio'])

    def test_falha_persistir_inicio_impede_qualquer_envio(self):
        execucao = self.diario.iniciar(self.lotes)
        # Falha real de persistência no ponto que antecede o envio.
        with patch('src.diario_impressao.sqlite3.connect', side_effect=PermissionError('Disco indisponível')):
            with self.assertRaises(RuntimeError):
                self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        self.assertEqual(self.diario.consultar()[0]['situacao'], 'pendente')

    def test_registro_invalido_preservado_sem_liberar_lote(self):
        self.caminho.write_bytes('arquivo inválido sintético'.encode('utf-8'))
        antes = self.caminho.read_bytes()
        with self.assertRaises(RuntimeError):
            DiarioImpressao(self.caminho)
        self.assertEqual(self.caminho.read_bytes(), antes)

    def test_limite_da_atividade_nao_apaga_historico_duravel(self):
        lotes = [{'setor': '10', 'ordens': [str(i).zfill(6) for i in range(1, 62)]}]
        execucao = self.diario.iniciar(lotes)
        for numero in lotes[0]['ordens']:
            self.diario.atualizar(execucao, numero, '10', 'envio_iniciado')
            self.diario.atualizar(execucao, numero, '10', 'concluido')
        self.assertEqual(len(DiarioImpressao(self.caminho).consultar()), 61)

    def test_parada_preserva_op_seguinte_sem_repetir_concluida(self):
        def executor(lotes, parar, atualizar, impressora):
            atualizar('atual', '000001', '10')
            atualizar('enviada', '000001', '10')
            parar.set()
        estado = EstadoImpressao(executor, self.impressoras, self.diario)
        estado.iniciar({'modo': 'lista', 'ordens': '1 2 3', 'setor': '10', 'impressora': 'Fila sintética'})
        estado.worker.join(3)
        self.assertEqual(estado.situacao()['fase'], 'interrompido')
        self.assertEqual([i['situacao'] for i in DiarioImpressao(self.caminho).consultar()], ['concluido', 'pendente', 'pendente'])

    def test_servico_nao_envia_quando_inicio_nao_pode_ser_persistido(self):
        efeito = Mock()
        def executor(lotes, parar, atualizar, impressora):
            atualizar('atual', '000001', '10')
            efeito()
        estado = EstadoImpressao(executor, self.impressoras, self.diario)
        with patch.object(self.diario, 'atualizar', side_effect=RuntimeError('Disco cheio')), self.assertLogs(level='ERROR'):
            estado.iniciar({'modo': 'lista', 'ordens': '1', 'setor': '10', 'impressora': 'Fila sintética'})
            estado.worker.join(3)
        efeito.assert_not_called()
        self.assertEqual(self.diario.consultar()[0]['situacao'], 'pendente')

    def test_falha_persistir_conclusao_mantem_envio_incerto_e_nao_conta(self):
        from src.servico_impressao import executar_lotes
        atualizar_real = self.diario.atualizar
        def atualizar(execucao, numero, setor, situacao):
            if situacao == 'concluido':
                raise RuntimeError('Falha ao salvar conclusão')
            atualizar_real(execucao, numero, setor, situacao)
        estado = EstadoImpressao(executar_lotes, self.impressoras, self.diario)
        with patch('src.handle_app.inicia_app', return_value=(None, {})), \
             patch('src.handle_app.preencher_dados_fixos'), \
             patch('main.processar_ordem', return_value=True) as envio, \
             patch('src.servico_impressao.registrar_evento') as metricas, \
             patch.object(self.diario, 'atualizar', side_effect=atualizar), self.assertLogs(level='ERROR'):
            estado.iniciar({'modo': 'lista', 'ordens': '1 2', 'setor': '10', 'impressora': 'Fila sintética'})
            estado.worker.join(3)
        envio.assert_called_once()
        metricas.assert_not_called()
        self.assertEqual([i['situacao'] for i in self.diario.consultar()], ['incerto', 'pendente'])
        with self.assertRaises(RuntimeError):
            self.diario.iniciar(self.lotes)
