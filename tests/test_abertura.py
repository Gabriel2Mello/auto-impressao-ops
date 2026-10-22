"""Diário, enumeração e servidor separados, sem Sisplan ou envio de impressão."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from integracao_hub import MedidorAbertura
from src.diario_impressao import DiarioImpressao
from src.impressoras import Impressoras
from src.interface_web import criar_servidor
from src.servico_impressao import EstadoImpressao


class TestAbertura(unittest.TestCase):
    def test_tempos_separados_de_diario_impressoras_e_servidor(self):
        with TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            medidor = MedidorAbertura('impressao-ops', pasta)
            listar = Mock(return_value=['Fila sintética'])
            executor = Mock()
            with patch('src.servico_impressao.DiarioImpressao', side_effect=lambda: DiarioImpressao(pasta / 'diario.sqlite3')), \
                    patch('src.servico_impressao.Impressoras', side_effect=lambda: Impressoras(pasta / 'preferencia.json', listar)):
                estado = EstadoImpressao(executor=executor, medidor_abertura=medidor)
            servidor, _ = criar_servidor(estado, porta=0, medidor_abertura=medidor)
            servidor.server_close()
            linhas = [json.loads(linha) for linha in
                      (pasta / 'logs/impressao-ops-abertura.log').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([linha['etapa'] for linha in linhas if linha['situacao'] == 'concluida'],
                             ['diario_local', 'impressoras_windows', 'servidor_local'])
            self.assertFalse((pasta / 'preferencia.json').exists())
            executor.assert_not_called()
            listar.assert_called_once()

    def test_falha_do_diario_nao_e_ocultada_pelo_medidor(self):
        with TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            medidor = MedidorAbertura('impressao-ops', pasta)
            erro = RuntimeError('mensagem-privada-sintetica')
            with patch('src.servico_impressao.DiarioImpressao', side_effect=erro), \
                    self.assertRaises(RuntimeError) as captura:
                EstadoImpressao(medidor_abertura=medidor)
            self.assertIs(captura.exception, erro)
            conteudo = (pasta / 'logs/impressao-ops-abertura.log').read_text(encoding='utf-8')
            self.assertNotIn('mensagem-privada-sintetica', conteudo)
            self.assertEqual(json.loads(conteudo.splitlines()[-1])['situacao'], 'falhou')
