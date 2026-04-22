from time import sleep

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

    campos = inicia_app()
    preencher_dados_fixos(campos)

    for i in range(int(inicio), int(fim) + 1):
        numero = f'{i:06}'
        print(f'\nImprimindo: {numero}')

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



if __name__ == '__main__':
    main()
