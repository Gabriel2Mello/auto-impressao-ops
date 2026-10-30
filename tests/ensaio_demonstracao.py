"""Ensaio da demonstração completa no WebView2, usando somente filas fictícias."""
from threading import Thread
import time
from unittest.mock import patch

import demonstracao
from desktop_impressao import Janela, executar


def main():
    falhas = []

    class Ensaio(Janela):
        def executar(self):
            def verificar():
                import webview
                try:
                    limite = time.monotonic() + 30
                    while not webview.windows:
                        assert time.monotonic() < limite, 'Janela ausente'
                        time.sleep(.1)
                    janela = webview.windows[0]
                    assert janela.events.loaded.wait(30)
                    def esperar(expressao):
                        for _ in range(150):
                            if janela.evaluate_js(expressao):
                                return
                            time.sleep(.1)
                        raise AssertionError(expressao)
                    esperar("online && !!document.getElementById('demo-exemplo').onclick")
                    assert 'Demonstração' in self.nome
                    assert self.app_id.endswith('.Demo')
                    for resultado in ['sucesso', 'erro']:
                        janela.evaluate_js(f"document.getElementById('demo-resultado').value='{resultado}';document.getElementById('demo-resultado').dispatchEvent(new Event('change'))")
                        esperar('!pendente')
                        janela.evaluate_js("document.getElementById('demo-exemplo').click();document.getElementById('conferir').click()")
                        esperar('conferido !== null && !pendente')
                        assert janela.evaluate_js("document.getElementById('resumo-progresso').hidden && document.getElementById('fase').textContent === 'Conferido'")
                        janela.evaluate_js("document.getElementById('imprimir').click()")
                        esperar('ocupado')
                        assert janela.evaluate_js("!document.getElementById('tabela-conferencia').hidden && document.getElementById('acoes-impressao').hidden")
                        esperar('!ocupado && !pendente')
                        if resultado == 'sucesso':
                            assert janela.evaluate_js("document.getElementById('enviadas').textContent === '5'")
                        else:
                            assert janela.evaluate_js("!document.getElementById('pendencias').hidden")
                    assert 'src.handle_app' not in __import__('sys').modules
                except Exception as erro:
                    falhas.append(repr(erro))
                finally:
                    self.servidor.encerrar()
            thread = Thread(target=verificar)
            thread.start()
            try:
                super().executar()
            finally:
                thread.join()

    with patch('desktop_impressao.executar', side_effect=lambda servidor: executar(servidor, fabrica=Ensaio)):
        demonstracao.main()
    if falhas:
        raise RuntimeError('; '.join(falhas))
    print('Demonstração WebView2: exemplo, conferência, sucesso e falha aprovados; Sisplan não importado.')


if __name__ == '__main__':
    main()
