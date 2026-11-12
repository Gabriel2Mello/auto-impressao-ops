"""Inicia Impressão de OPs desktop; --web mantém o painel no navegador."""

import logging
import os
from pathlib import Path
import sys
from contextlib import ExitStack
from integracao_hub import ConflitoAplicacao, IntegracaoLocal, MedidorAbertura, executar_interface
from sincronizar_estatisticas import Sincronizador



def informar_falha(mensagem):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, 'Impressão de OPs', 0x10)
    else:
        print(mensagem, file=sys.stderr)


def main(publicacao: IntegracaoLocal, *, desktop=False, portal=None):
    with MedidorAbertura('impressao-ops') as medidor, ExitStack() as recursos:
        with medidor.etapa('sincronizacao'):
            sincronizador = recursos.enter_context(Sincronizador(aplicacao='impressao-ops', relatar=logging.getLogger(__name__).info))
        try:
            return executar_painel(publicacao, medidor, desktop=desktop, portal=portal)
        finally:
            # A janela já saiu após a OP atual; a exclusividade acompanha o processo.
            recursos.close()
            if sincronizador.worker is not None:
                sincronizador.worker.join()


def executar_painel(publicacao: IntegracaoLocal, medidor=None, *, desktop=False, portal=None):
    medidor = medidor or MedidorAbertura('impressao-ops')
    with medidor.etapa('importacoes'):
        from src.interface_web import criar_servidor
        from src.utils import DIRETORIO_APLICACAO
    try:
        with medidor.etapa('log_operacional'):
            logging.basicConfig(filename=DIRETORIO_APLICACAO / 'impressao.log',
                                level=logging.INFO, encoding='utf-8',
                                format='%(asctime)s %(levelname)s %(message)s')
        with medidor.etapa('preparacao_painel'):
            servidor, estado = criar_servidor(medidor_abertura=medidor, modo_desktop=desktop,
                                            porta=portal.porta_executor if portal else (0 if desktop else 8766),
                                            portal=portal,
                                            reservar_sisplan=publicacao.reservar_sisplan if portal else None)
    except (OSError, RuntimeError) as erro:
        publicacao.registrar_falha(erro)
        mensagem = ('Não foi possível abrir o painel. Verifique se o programa já está aberto '
                    f'ou se a pasta permite gravar o log e o diário de impressão.\n{erro}')
        if portal is not None:
            print(mensagem, file=sys.stderr)
        else:
            informar_falha(mensagem)
        return 1
    try:
        with medidor.etapa('publicacao'):
            if desktop:
                publicacao.registro['desktop'] = 1
            publicacao.publicar(servidor, servidor.encerrar,
                lambda: {'encerrando': servidor.fechando, 'paginas': len(servidor.paginas),
                         'ocupado': estado.worker is not None and estado.worker.is_alive()})
        if desktop:
            from desktop_impressao import executar
            executar(servidor)
        else:
            servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        estado.encerrar()
        servidor.server_close()
        if estado.worker is not None:
            estado.worker.join()
    return 0


def iniciar_portal(argumentos):
    from ctypes import byref, windll
    from ctypes.wintypes import DWORD

    from src.portal_ops import ler_config_portal

    if len(argumentos) != 1:
        print('Uso: Impressao OPs.exe --portal <caminho de portal.json>', file=sys.stderr)
        return 2
    try:
        portal = ler_config_portal(Path(argumentos[0]))
    except (OSError, ValueError):
        print('Não foi possível carregar a configuração privada do portal.', file=sys.stderr)
        return 2
    sessao = DWORD()
    if not windll.kernel32.ProcessIdToSessionId(os.getpid(), byref(sessao)) or not sessao.value:
        print('Abra o executor na sessão Windows interativa que contém o Sisplan.', file=sys.stderr)
        return 2
    os.environ['NUNES_OPS_API_PORTA'] = str(portal.porta_api)
    try:
        with IntegracaoLocal('impressao-ops', 'Impressão de OPs', True, sem_navegador=True,
                             sisplan_por_operacao=True) as publicacao:
            return main(publicacao, portal=portal)
    except ConflitoAplicacao as erro:
        print(str(erro), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if sys.argv[1:2] == ['--portal']:
        raise SystemExit(iniciar_portal(sys.argv[2:]))
    if '--demo' in sys.argv:
        from demonstracao import main as demonstrar
        raise SystemExit(demonstrar())
    if '--web' in sys.argv:
        sys.argv.remove('--web')
        raise SystemExit(executar_interface('impressao-ops', 'Impressão de OPs', True, main))
    from desktop_impressao import iniciar
    raise SystemExit(iniciar())
