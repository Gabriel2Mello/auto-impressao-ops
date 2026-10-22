"""Inicia a interface web local de impressão de OPs."""

import logging
import sys
from integracao_hub import IntegracaoLocal, executar_interface
from sincronizar_estatisticas import Sincronizador



def informar_falha(mensagem):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, 'Impressão de OPs', 0x10)
    else:
        print(mensagem, file=sys.stderr)


def main(publicacao: IntegracaoLocal):
    with Sincronizador(aplicacao='impressao-ops', relatar=logging.getLogger(__name__).info):
        return executar_painel(publicacao)


def executar_painel(publicacao: IntegracaoLocal):
    from src.interface_web import criar_servidor
    from src.utils import DIRETORIO_APLICACAO
    try:
        logging.basicConfig(filename=DIRETORIO_APLICACAO / 'impressao.log',
                            level=logging.INFO, encoding='utf-8',
                            format='%(asctime)s %(levelname)s %(message)s')
        servidor, estado = criar_servidor()
    except (OSError, RuntimeError) as erro:
        publicacao.registrar_falha(erro)
        informar_falha(f'Não foi possível abrir o painel. Verifique se o programa já está aberto '
                       f'ou se a pasta permite gravar o log e o diário de impressão.\n{erro}')
        return 1
    try:
        publicacao.publicar(servidor, servidor.encerrar,
            lambda: {'encerrando': servidor.fechando, 'paginas': len(servidor.paginas)})
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        estado.encerrar()
        servidor.server_close()
        if estado.worker is not None:
            estado.worker.join()
    return 0


if __name__ == '__main__':
    raise SystemExit(executar_interface('impressao-ops', 'Impressão de OPs', True, main))
