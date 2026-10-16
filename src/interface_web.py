"""Painel HTTP restrito ao próprio computador, sem dependências web adicionais."""

from integracao_hub import atender_integracao

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import compare_digest, token_urlsafe
from threading import Event, RLock, Thread
from time import monotonic
from urllib.parse import urlsplit

from src.entrada_web import montar_lotes
from src.servico_impressao import ConflitoExecucao, EstadoImpressao
from src.utils import DIRETORIO_APLICACAO


class ServidorInterface(ThreadingHTTPServer):
    daemon_threads = True
    ESPERA_FECHAMENTO = 3

    def __init__(self, manipulador, estado, porta):
        super().__init__(('127.0.0.1', porta), manipulador)
        self.estado = estado
        self.trava_paginas = RLock()
        self.paginas = {}
        self.teve_pagina = False
        self.sem_paginas_desde = None
        self.fechando = False
        self.criado_em = monotonic()
        self.parar_conexoes = Event()

    def abrir_pagina(self, pagina):
        with self.trava_paginas:
            if self.fechando:
                raise ValueError('O programa está encerrando.')
            anterior = self.paginas.get(pagina)
            if anterior is not None:
                anterior.set()
            presenca = Event()
            self.paginas[pagina] = presenca
            self.teve_pagina = True
            self.sem_paginas_desde = None
            return presenca

    def fechar_pagina(self, pagina, presenca=None):
        with self.trava_paginas:
            atual = self.paginas.get(pagina)
            if atual is not None and (presenca is None or atual is presenca):
                self.paginas.pop(pagina)
                atual.set()
                if not self.paginas:
                    self.sem_paginas_desde = monotonic()

    def encerrar(self):
        with self.trava_paginas:
            if self.fechando:
                return
            self.fechando = True
        self.estado.encerrar()
        Thread(target=self.shutdown, daemon=True).start()

    def service_actions(self):
        with self.trava_paginas:
            if not self.teve_pagina and monotonic() - self.criado_em >= 120:
                self.encerrar()
                return
            if (self.teve_pagina and not self.paginas and self.sem_paginas_desde is not None
                    and monotonic() - self.sem_paginas_desde >= self.ESPERA_FECHAMENTO):
                self.encerrar()

    def shutdown(self):
        self.parar_conexoes.set()
        super().shutdown()

    def server_close(self):
        self.parar_conexoes.set()
        self.estado.encerrar()
        super().server_close()


def criar_servidor(estado=None, porta=8766):
    estado = estado if estado is not None else EstadoImpressao()
    token = token_urlsafe(32)
    recursos = {
        '/': ('src/impressao.html', 'text/html; charset=utf-8'),
        '/impressao.css': ('src/impressao.css', 'text/css; charset=utf-8'),
        '/impressao.js': ('src/impressao.js', 'text/javascript; charset=utf-8'),
        '/icons/icone.svg': ('icons/icone.svg', 'image/svg+xml'),
        '/favicon.ico': ('icons/icone.ico', 'image/x-icon'),
        '/icons/icone-192.png': ('icons/icone-192.png', 'image/png'),
    }

    class Manipulador(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, formato, *args):
            pass

        def host_valido(self):
            return self.headers.get_all('Host') == [f'127.0.0.1:{servidor.server_port}']

        def autorizado(self):
            origem = f'http://127.0.0.1:{servidor.server_port}'
            return (self.host_valido()
                    and compare_digest(self.headers.get('Authorization', ''), f'Bearer {token}')
                    and self.headers.get('Origin') in ((origem,) if self.command == 'POST' else (None, origem)))

        def responder(self, status, conteudo, tipo='application/json; charset=utf-8'):
            if not isinstance(conteudo, bytes):
                conteudo = json.dumps(conteudo, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(conteudo)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(conteudo)

        def acompanhar(self):
            pagina = self.headers.get('X-Impressao-Pagina', '')
            if not pagina or len(pagina) > 100 or not pagina.isascii():
                self.responder(400, {'erro': 'Identificação da página inválida.'})
                return
            try:
                presenca = servidor.abrir_pagina(pagina)
            except ValueError as erro:
                self.responder(503, {'erro': str(erro)})
                return
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                ultimo_estado = None
                while not servidor.parar_conexoes.is_set() and not presenca.is_set():
                    situacao = json.dumps(estado.situacao(), ensure_ascii=False)
                    if situacao != ultimo_estado:
                        self.wfile.write(f'data: {situacao}\n\n'.encode('utf-8'))
                        ultimo_estado = situacao
                    else:
                        # Mantém apenas a conexão viva; não envia estado nem atualiza a tela.
                        self.wfile.write(b': conexao\n\n')
                    self.wfile.flush()
                    if presenca.wait(1):
                        break
            except (OSError, ValueError):
                # A desconexão da aba é o encerramento normal deste canal.
                pass
            finally:
                servidor.fechar_pagina(pagina, presenca)

        def do_GET(self):
            if atender_integracao(self):
                return
            caminho = urlsplit(self.path).path
            if not self.host_valido():
                self.responder(403, {'erro': 'Acesso não autorizado.'})
            elif caminho in recursos:
                arquivo, tipo = recursos[caminho]
                conteudo = (DIRETORIO_APLICACAO / arquivo).read_bytes()
                if caminho == '/':
                    conteudo = conteudo.replace(b'__TOKEN__', token.encode('ascii'))
                self.responder(200, conteudo, tipo)
            elif not self.autorizado():
                self.responder(403, {'erro': 'Acesso não autorizado.'})
            elif caminho == '/api/estado':
                self.responder(200, estado.situacao())
            elif caminho == '/api/acompanhar':
                self.acompanhar()
            elif caminho == '/api/impressoras':
                try:
                    self.responder(200, estado.listar_impressoras())
                except ConflitoExecucao as erro:
                    self.responder(409, {'erro': str(erro)})
            else:
                self.responder(404, {'erro': 'Recurso não encontrado.'})

        def do_POST(self):
            if atender_integracao(self):
                return
            if not self.autorizado():
                self.close_connection = True
                self.responder(403, {'erro': 'Acesso não autorizado.'})
                return
            try:
                tamanhos = self.headers.get_all('Content-Length', [])
                if (len(tamanhos) != 1 or not tamanhos[0].isascii() or not tamanhos[0].isdigit()
                        or not 1 <= int(tamanhos[0]) <= 100000
                        or self.headers.get('Transfer-Encoding') is not None
                        or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json'):
                    self.close_connection = True
                    raise ValueError('Solicitação inválida ou muito grande.')
                dados = json.loads(self.rfile.read(int(tamanhos[0])))
                if not isinstance(dados, dict):
                    raise ValueError('Solicitação inválida.')
                caminho = urlsplit(self.path).path
                if caminho == '/api/conferir':
                    lotes = montar_lotes(dados)
                    self.responder(200, {'lotes': lotes, 'total': sum(len(lote['ordens']) for lote in lotes)})
                    return
                if caminho == '/api/iniciar':
                    estado.iniciar(dados)
                elif caminho == '/api/impressora':
                    estado.selecionar_impressora(dados.get('impressora'))
                elif caminho == '/api/parar':
                    estado.solicitar_parada()
                elif caminho == '/api/encerrar':
                    servidor.encerrar()
                elif caminho == '/api/fechar-pagina':
                    pagina = dados.get('pagina')
                    if not isinstance(pagina, str) or not pagina or len(pagina) > 100:
                        raise ValueError('Identificação da página inválida.')
                    servidor.fechar_pagina(pagina)
                else:
                    self.responder(404, {'erro': 'Recurso não encontrado.'})
                    return
                self.responder(200, estado.situacao())
            except ConflitoExecucao as erro:
                self.responder(409, {'erro': str(erro)})
            except (ValueError, RuntimeError) as erro:
                self.responder(400, {'erro': str(erro)})

    servidor = ServidorInterface(Manipulador, estado, porta)
    return servidor, estado
