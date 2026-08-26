from time import sleep, perf_counter
from pathlib import Path

from pywinauto.keyboard import send_keys

from src.handle_app import (
    fecha_menu_impressao,
    inicia_app,
    ATALHOS,
    preencher_dados_fixos,
    handle_mini_menu,
    handle_menu_impressao,
    aguardar,
)
from src.utils import obter_lotes

MIN_SLEEP_SECONDS = 1
MAX_TENTATIVAS = 2
MODO_ENTRADA = 'arquivo' # 'arquivo', 'intervalos'


def processar_ordem(app, campos, numero):
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        mensagem = '\nConsultando' if tentativa == 1 else 'Tentando novamente'
        print(f'{mensagem}: {numero}')

        try:
            campo_numero = campos['numero']
            aguardar(campo_numero).set_text(numero)

            send_keys(ATALHOS['consultar'])
            sleep(MIN_SLEEP_SECONDS)

            print('Imprimindo')
            send_keys(ATALHOS['imprimir'])
            sleep(MIN_SLEEP_SECONDS)

            if not handle_mini_menu(app):
                raise RuntimeError('Falha no mini menu de impressão.')

            if not handle_menu_impressao(app):
                raise RuntimeError('Falha no menu de impressão.')

            return True

        except Exception as e:
            fecha_menu_impressao(app)

            if tentativa < MAX_TENTATIVAS:
                sleep(MIN_SLEEP_SECONDS)

    raise RuntimeError('Alerta: Falha no fluxo de impressão.')


def processar_lote(app, campos, lote):
    setor = lote['setor']
    preencher_dados_fixos(campos, setor)

    print(f'\nIniciando setor {setor}: {len(lote["ordens"])} ordens.')

    for numero in lote['ordens']:
        processar_ordem(app, campos, numero)

    print(f'Setor {setor} concluído.')


def main():
    start_time = perf_counter()

    try:
        lotes = obter_lotes(MODO_ENTRADA)

        if not lotes:
            print('Nenhuma ondem informada.')
            return

        app, campos = inicia_app()

        for lote in lotes:
            processar_lote(app, campos, lote)

    except Exception as e:
        print(f'\nERRO: {e}')
    finally:
        elapsed_time = perf_counter() - start_time

        print(f'\nTerminado em {elapsed_time:0.2f} segundos')
        input('Pressione Enter para fechar...')


if __name__ == '__main__':
    main()

