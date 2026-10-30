"""Ciclo desktop e autenticação com estado sintético; não acessa Sisplan."""
import io
import json
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import desktop_impressao as desktop
import desktop_preferencias
from tests.test_interface_web import ComImpressoras
from src.interface_web import criar_servidor
from src.servico_impressao import EstadoImpressao


class TestDesktop(ComImpressoras):
    def test_janela_aguarda_op_em_andamento_antes_de_ser_liberada(self):
        entrou, liberar = Event(), Event()

        def executor(lotes, parar, atualizar, impressora):
            atualizar('atual', '000001', '10')
            entrou.set()
            liberar.wait(3)
            atualizar('enviada', '000001', '10')
            self.assertTrue(parar.is_set())

        estado = EstadoImpressao(executor)
        estado.iniciar({'modo': 'lista', 'ordens': '1 2', 'setor': '10', 'impressora': self.nomes[0]})
        self.assertTrue(entrou.wait(3))
        servidor, _ = criar_servidor(estado, porta=0, modo_desktop=True)
        self.addCleanup(servidor.server_close)
        janela = desktop.Janela(servidor)

        def executar_janela():
            servidor.encerrar()
            try:
                self.assertFalse(janela.pronto_para_fechar.wait(.2))
            finally:
                liberar.set()
            self.assertTrue(janela.pronto_para_fechar.wait(3))
            self.assertFalse(estado.worker.is_alive())

        janela.executar = executar_janela
        desktop.executar(servidor, fabrica=lambda _: janela)
        self.assertEqual(estado.situacao()['enviadas'], 1)
        self.assertIsNone(servidor.desktop)

    def test_desktop_nao_encerra_por_perda_de_pagina(self):
        estado = EstadoImpressao(Mock())
        servidor, _ = criar_servidor(estado, porta=0, modo_desktop=True)
        self.addCleanup(servidor.server_close)
        servidor.criado_em = 0
        servidor.teve_pagina = True
        servidor.sem_paginas_desde = 0
        servidor.service_actions()
        self.assertFalse(servidor.fechando)

    def test_fechar_cancelado_preserva_execucao_e_confirmado_espera_salvamento(self):
        servidor = Mock(fechando=False)
        janela = desktop.Janela(servidor)
        nativa = Mock()
        nativa.events.loaded.is_set.return_value = True
        nativa.create_confirmation_dialog.return_value = False
        self.assertFalse(janela.fechar(nativa))
        servidor.encerrar.assert_not_called()
        janela.salvando = True
        nativa.evaluate_js.side_effect = lambda script, callback: callback(False)
        janela.salvar_e_encerrar(nativa)
        servidor.encerrar.assert_not_called()
        self.assertFalse(janela.salvando)
        nativa.evaluate_js.side_effect = lambda script, callback: callback(True)
        janela.salvar_e_encerrar(nativa)
        servidor.encerrar.assert_called_once_with(confirmado=True)


class TestAtivacao(unittest.TestCase):
    def pedido(self, **extras):
        cabecalhos = Message()
        for nome, valor in {'Host': '127.0.0.1:123', 'X-Nunes-Instancia': 'segredo',
                            'Content-Length': '2', 'Content-Type': 'application/json', **extras}.items():
            cabecalhos[nome] = valor
        registro = dict(protocolo=1, id='impressao-ops', instancia='sintetica', pid=123, token='segredo')
        handler = Mock(command='POST', headers=cabecalhos, rfile=io.BytesIO(b'{}'))
        handler.host_valido.return_value = True
        handler.server = Mock(fechando=False, integracao_nunes=Mock(registro=registro))
        return handler

    def test_ativacao_usa_token_de_instancia_e_recusa_pagina_web(self):
        for extras in [{'Origin': 'http://127.0.0.1:123'}, {'X-Nunes-Instancia': 'errado'},
                       {'Transfer-Encoding': 'chunked'}, {'Content-Length': '3'}]:
            with self.subTest(extras=extras):
                handler = self.pedido(**extras)
                desktop.atender_ativacao(handler)
                self.assertIn(handler.responder.call_args.args[0], (400, 403))
                handler.server.desktop.ativar.set.assert_not_called()
        handler = self.pedido()
        desktop.atender_ativacao(handler)
        self.assertEqual(handler.responder.call_args.args[0], 200)
        handler.server.desktop.ativar.set.assert_called_once()

    def test_tema_persistido_e_validacao_nao_alteram_preferencia_de_impressora(self):
        with TemporaryDirectory() as pasta, patch('desktop_preferencias.arquivo', return_value=Path(pasta) / 'tema.json'):
            self.assertEqual(desktop_preferencias.ler_tema(), 'escuro')
            desktop_preferencias.salvar_tema('claro')
            self.assertEqual(desktop_preferencias.ler_tema(), 'claro')
            with self.assertRaises(ValueError):
                desktop_preferencias.salvar_tema('../invalido')
            self.assertEqual(desktop_preferencias.ler_tema(), 'claro')


class TestFinalizacao(unittest.TestCase):
    def test_janela_liberada_nao_abandona_sincronizador_ou_retorna_antes_dele(self):
        import impressao
        janela_saiu, liberar = Event(), Event()
        sincronizador = Mock()
        sincronizador.__enter__ = Mock(return_value=sincronizador)
        sincronizador.__exit__ = Mock(return_value=False)
        sincronizador.worker = Thread(target=lambda: liberar.wait(3))
        sincronizador.worker.start()
        saidas = []
        with TemporaryDirectory() as pasta, \
                patch('impressao.MedidorAbertura', side_effect=lambda _: __import__('integracao_hub').MedidorAbertura('impressao-ops', Path(pasta))), \
                patch('impressao.Sincronizador', return_value=sincronizador), \
                patch('impressao.executar_painel', side_effect=lambda *a, **k: janela_saiu.set() or 0):
            processo = Thread(target=lambda: saidas.append(impressao.main(Mock(), desktop=True)))
            processo.start()
            try:
                self.assertTrue(janela_saiu.wait(2))
                self.assertTrue(processo.is_alive())
                self.assertEqual(saidas, [])
            finally:
                liberar.set()
                processo.join(3)
                sincronizador.worker.join(3)
        self.assertEqual(saidas, [0])


if __name__ == '__main__':
    unittest.main()
