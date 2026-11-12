"""Contrato entre o desktop e o CGI, sem acesso ao domínio, banco ou impressora."""

import json
import unittest
from unittest.mock import patch

from src.cliente_consulta_ops import consultar_localizacoes, consultar_pedidos
from src.protocolo_consulta_ops import ErroConsultaSisplan, ROTA_CONSULTA


ORDENS = ['000001', '000002']
LOCALIZACAO = dict(faccao='00001', faccao_nome='Facção sintética',
                   setor='20', setor_nome='Setor sintético', ordens=ORDENS)


class TestClienteConsulta(unittest.TestCase):
    def consultar(self):
        return consultar_localizacoes([{'ordens': ORDENS}])

    @patch('src.cliente_consulta_ops._postar')
    def test_busca_por_pedido_e_valida_formato_e_unicidade_das_ops(self, postar):
        pedidos = ['2026-1234']
        postar.return_value = 200, json.dumps({'lotes': [LOCALIZACAO]}).encode()
        self.assertEqual(consultar_pedidos(pedidos), [LOCALIZACAO])
        self.assertEqual(json.loads(postar.call_args.args[1]), {'pedidos': pedidos})
        for lotes in ([], [dict(LOCALIZACAO, ordens=['1'])],
                      [LOCALIZACAO, dict(LOCALIZACAO, setor='30')]):
            postar.return_value = 200, json.dumps({'lotes': lotes}).encode()
            with self.subTest(lotes=lotes), self.assertRaises(ErroConsultaSisplan):
                consultar_pedidos(pedidos)

    @patch.dict('os.environ', {'NUNES_OPS_API_PORTA': '9443'})
    @patch('src.cliente_consulta_ops._postar')
    def test_envia_apenas_numeros_e_valida_retorno(self, postar):
        postar.return_value = 200, json.dumps({'lotes': [LOCALIZACAO]}).encode()
        self.assertEqual(self.consultar(), [LOCALIZACAO])
        url, corpo = postar.call_args.args
        self.assertEqual(url, f'https://ts01.gratitude.local:9443{ROTA_CONSULTA}')
        self.assertEqual(json.loads(corpo), {'ordens': ORDENS})

    @patch.dict('os.environ', {'NUNES_OPS_API_PORTA': '443'})
    @patch('src.cliente_consulta_ops._postar')
    def test_recusa_respostas_incompletas_repetidas_ou_inesperadas(self, postar):
        for ordens in (['000001'], ['000001', '000001'], ['000001', '000003']):
            postar.return_value = 200, json.dumps({'lotes': [dict(LOCALIZACAO, ordens=ordens)]}).encode()
            with self.subTest(ordens=ordens), self.assertRaisesRegex(ErroConsultaSisplan, 'indisponível'):
                self.consultar()

    @patch.dict('os.environ', {'NUNES_OPS_API_PORTA': '443'})
    @patch('src.cliente_consulta_ops._postar')
    def test_recusa_acesso_e_exibe_erro_de_negocio(self, postar):
        for status in (401, 403):
            postar.return_value = status, b''
            with self.subTest(status=status), self.assertRaisesRegex(ErroConsultaSisplan, 'conta Windows'):
                self.consultar()
        postar.return_value = 422, b'{"erro":"OP sem saldo."}'
        with self.assertRaisesRegex(ErroConsultaSisplan, 'OP sem saldo'):
            self.consultar()

    @patch.dict('os.environ', {'NUNES_OPS_API_PORTA': '443'})
    @patch('src.cliente_consulta_ops._postar', side_effect=TimeoutError('Detalhe privado.'))
    def test_falha_de_transporte_bloqueia_a_consulta(self, postar):
        with self.assertRaisesRegex(ErroConsultaSisplan, '^Consulta ao Sisplan indisponível'):
            self.consultar()
