from pathlib import Path
import os
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.servico_impressao import EstadoImpressao
from metricas_nunes import consultar_metricas, registrar_evento


class TestDiario(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'NUNES_METRICAS_DADOS': pasta}))
        self.caminho = Path(pasta) / 'execucoes.sqlite3'
        self.lotes = [{'setor': '10', 'ordens': ['000001', '000002', '000003']}]
        self.diario = DiarioImpressao(self.caminho)
        self.impressoras = Impressoras(Path(pasta) / 'config.json', listar=lambda: ['Fila sintética'])
        self.impressoras.selecionar('Fila sintética')

    def metricas(self):
        return consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})

    def test_metricas_indisponiveis_sao_recuperadas_com_identidade_e_instante_originais(self):
        execucao = self.diario.iniciar(self.lotes)
        self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        with patch('src.diario_impressao.registrar_evento', return_value=False):
            self.diario.atualizar(execucao, '1', '10', 'concluido')
        envio = self.diario.consultar()[0]
        self.assertEqual(self.metricas()['totais']['op_enviada'], 0)
        DiarioImpressao(self.caminho)
        dados = self.metricas()
        self.assertEqual(dados['totais']['op_enviada'], 1)
        self.assertEqual(dados['historico'][0]['ocorrido_em'], envio['atualizado_em'])
        self.assertEqual(dados['historico'][0]['execucao'], execucao)
        DiarioImpressao(self.caminho)
        self.assertEqual(self.metricas()['totais']['op_enviada'], 1)

    def test_queda_apos_aceite_da_metrica_nao_duplica_na_reabertura(self):
        execucao = self.diario.iniciar(self.lotes)
        self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        def aceitar_sem_confirmar(*args, **kwargs):
            self.assertTrue(registrar_evento(*args, **kwargs))
            raise RuntimeError('Queda sintética após aceite')
        with patch('src.diario_impressao.registrar_evento', side_effect=aceitar_sem_confirmar), self.assertLogs(level='ERROR'):
            self.diario.atualizar(execucao, '1', '10', 'concluido')
        self.assertEqual(self.metricas()['totais']['op_enviada'], 1)
        DiarioImpressao(self.caminho)
        self.assertEqual(self.metricas()['totais']['op_enviada'], 1)
        with self.diario.conectar() as banco:
            self.assertEqual(banco.execute('SELECT count(*) FROM metricas').fetchone()[0], 0)

    def test_migracao_v1_preserva_historico_sem_republicar_conclusoes_antigas(self):
        execucao = self.diario.iniciar(self.lotes)
        self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        with self.diario.conectar() as banco:
            banco.execute("UPDATE envios SET situacao='concluido' WHERE numero='000001'")
            banco.execute('DROP TABLE metricas')
            banco.execute('PRAGMA user_version=1')
        antes = self.diario.consultar()
        migrado = DiarioImpressao(self.caminho)
        self.assertEqual(migrado.consultar(), antes)
        self.assertEqual(self.metricas()['totais']['op_enviada'], 0)
        novo = migrado.iniciar([{'setor': '10', 'ordens': ['000001']}])
        migrado.atualizar(novo, '1', '10', 'envio_iniciado')
        migrado.atualizar(novo, '1', '10', 'concluido')
        self.assertEqual(self.metricas()['totais']['op_enviada'], 1)

    def test_falha_criar_metrica_desfaz_conclusao_sem_registrar_envio(self):
        execucao = self.diario.iniciar(self.lotes)
        self.diario.atualizar(execucao, '1', '10', 'envio_iniciado')
        with self.diario.conectar() as banco:
            banco.execute("CREATE TRIGGER falhar BEFORE INSERT ON metricas BEGIN SELECT RAISE(ABORT, 'sintetico'); END")
        with self.assertRaises(RuntimeError):
            self.diario.atualizar(execucao, '1', '10', 'concluido')
        self.assertEqual(self.diario.consultar()[0]['situacao'], 'envio_iniciado')
        self.assertEqual(self.metricas()['totais']['op_enviada'], 0)

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
        self.assertEqual(chamadas, ['envio'])
        self.assertEqual(reaberto.situacao()['historico'][0]['situacao'], 'incerto')
        # Abrir o painel não repete nada. Um novo pedido usa apenas o novo lote.
        recebidos = []
        reaberto.executor = lambda lotes, *_: recebidos.extend(lotes[0]['ordens'])
        reaberto.iniciar({'modo': 'lista', 'ordens': '4', 'impressora': 'Fila sintética'})
        reaberto.worker.join(3)
        self.assertEqual(recebidos, ['000004'])
        self.assertEqual([i['numero'] for i in reaberto.situacao()['historico']], ['000004'])
        self.assertEqual(self.diario.consultar()[0]['situacao'], 'incerto')
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
             patch('src.diario_impressao.registrar_evento') as metricas, \
             patch.object(self.diario, 'atualizar', side_effect=atualizar), self.assertLogs(level='ERROR'):
            estado.iniciar({'modo': 'lista', 'ordens': '1 2', 'setor': '10', 'impressora': 'Fila sintética'})
            estado.worker.join(3)
        envio.assert_called_once()
        metricas.assert_not_called()
        self.assertEqual([i['situacao'] for i in self.diario.consultar()], ['incerto', 'pendente'])
        with self.assertRaises(RuntimeError):
            self.diario.iniciar(self.lotes)
