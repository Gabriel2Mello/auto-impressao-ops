import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.impressoras import Impressoras


class TestImpressoras(unittest.TestCase):
    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.config = Path(pasta.name) / 'Nunes' / 'config.json'
        self.listar = Mock(return_value=['HP da produção', 'EPSON', 'HP da produção', r'\\servidor\Facção'])
        ambiente = patch.dict('os.environ', {'IMPRESSORA_OP': 'EPSON'})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def gerenciar(self):
        return Impressoras(self.config, self.listar)

    def test_primeiro_uso_aproveita_variavel_e_ordena_sem_duplicatas(self):
        filas = self.gerenciar()
        self.assertEqual(filas.situacao()['impressora'], 'EPSON')
        self.assertEqual(filas.nomes, sorted(set(self.listar.return_value), key=str.casefold))
        self.assertFalse(self.config.exists())

    def test_selecao_so_persiste_ao_usar_e_restauracao_precede_variavel(self):
        filas = self.gerenciar()
        filas.selecionar(r'\\servidor\Facção')
        self.assertFalse(self.config.exists())
        filas.registrar_uso(filas.selecionada)
        self.assertEqual(self.gerenciar().situacao()['impressora'], r'\\servidor\Facção')
        self.assertEqual(list(self.config.parent.glob('*.tmp')), [])

    def test_removida_nao_troca_para_variavel_e_pode_reaparecer(self):
        filas = self.gerenciar()
        filas.registrar_uso('HP da produção')
        self.listar.return_value = ['EPSON']
        restaurada = self.gerenciar()
        self.assertEqual(restaurada.situacao()['impressora'], '')
        self.assertIn('HP da produção', restaurada.situacao()['aviso_impressora'])
        self.listar.return_value.append('HP da produção')
        self.assertEqual(restaurada.atualizar()['impressora'], 'HP da produção')

    def test_estado_nao_consulta_windows_periodicamente(self):
        filas = self.gerenciar()
        self.listar.reset_mock()
        for _ in range(10):
            filas.situacao()
        self.listar.assert_not_called()

    def test_configuracao_corrompida_nao_impede_selecionar(self):
        self.config.parent.mkdir(parents=True)
        for conteudo in ['{invalido', '[]', '{}', '{"ultima_impressora": 3}', '{"ultima_impressora": ""}']:
            with self.subTest(conteudo=conteudo):
                self.config.write_text(conteudo, encoding='utf-8')
                with self.assertLogs(level='WARNING'):
                    filas = self.gerenciar()
                filas.selecionar('HP da produção')
                filas.registrar_uso('HP da produção')
                self.assertEqual(json.loads(self.config.read_text(encoding='utf-8'))['ultima_impressora'], 'HP da produção')

    def test_erro_de_consulta_e_lista_vazia_sao_recuperaveis(self):
        self.listar.side_effect = RuntimeError('Serviço indisponível')
        filas = self.gerenciar()
        self.assertIn('Serviço indisponível', filas.situacao()['aviso_impressora'])
        self.listar.side_effect = None
        self.listar.return_value = []
        self.assertEqual(filas.atualizar()['impressora'], '')
        with self.assertRaises(ValueError):
            filas.selecionar(None)
        self.listar.return_value = ['EPSON']
        self.assertEqual(filas.atualizar()['impressora'], 'EPSON')


if __name__ == '__main__':
    unittest.main()
