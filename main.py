from time import sleep, perf_counter

from pywinauto.keyboard import send_keys

from src.handle_app import (
    inicia_app,
    ATALHOS,
    preencher_dados_fixos,
    handle_mini_menu,
    handle_menu_impressao
)


def main():
    inicio = input('De: ').strip()
    fim = input('Para: ').strip()

    start_time = perf_counter()

    campos = inicia_app()
    preencher_dados_fixos(campos)

    print('\nIniciando processo...')
    for i in range(int(inicio), int(fim) + 1):
        numero = f'{i:06}'
        print(f'Imprimindo: {numero}')

        campos['numero'].set_text(numero)

        send_keys(ATALHOS['consultar'])
        sleep(2)

        send_keys(ATALHOS['imprimir'])
        sleep(0.4)

        handle_mini_menu()

        send_keys(ATALHOS['ok'])
        sleep(0.3)

        handle_menu_impressao()
        sleep(1.5)

    elapsed_time = perf_counter() - start_time
    print(f'\nTerminado em {elapsed_time:0.2f} segundos')
    input('Pressione Enter para fechar...')



if __name__ == '__main__':
    main()
