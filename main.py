from time import sleep, perf_counter

from pywinauto.keyboard import send_keys

from src.handle_app import (
    inicia_app,
    ATALHOS,
    preencher_dados_fixos,
    handle_mini_menu,
    handle_menu_impressao
)


def input_numeros():
    try:
        inicio_str = input('De: ').strip()
        fim_str = input('Para:' ).strip()

        if not inicio_str or not fim_str:
            return None, None

        inicio, fim = int(inicio_str), int(fim_str)

        if inicio >= fim:
            print('\nErro: Número inicial maior que o final.')
            return None, None

        return inicio, fim
    except ValueError:
        print("\nErro: Digite apenas números.")
        return None, None


def main():
    inicio, fim = input_numeros()
    if inicio is None or fim is None:
        input('Pressione Enter para Fechar...')
        return

    start_time = perf_counter()

    try:
        campos = inicia_app()
        preencher_dados_fixos(campos)

        print('\nIniciando impressão...')
        for i in range(inicio, fim + 1):
            numero = f'{i:06}'
            print(f'Processando: {numero}')

            campos['numero'].set_text(numero)

            send_keys(ATALHOS['consultar'])
            sleep(3)

            send_keys(ATALHOS['imprimir'])
            sleep(1)

            handle_mini_menu()
            handle_menu_impressao()
            sleep(1.5)

    except Exception as e:
        print(f'ERRO: {e}')
    finally:
        elapsed_time = perf_counter() - start_time
        print(f'\nTerminado em {elapsed_time:0.2f} segundos')
        input('Pressione Enter para fechar...')



if __name__ == '__main__':
    main()

