from time import sleep, perf_counter
from pywinauto import Desktop

from pywinauto.keyboard import send_keys # type: ignore

from src.handle_app import (
    fecha_menu_impressao,
    inicia_app,
    ATALHOS,
    preencher_dados_fixos,
    handle_mini_menu,
    handle_menu_impressao
)


def input_numeros():
    try:
        inicio_str = input('De:  ').strip()
        fim_str    = input('Até: ' ).strip()

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
    MAX_TENTATIVAS = 2

    try:
        app, campos = inicia_app()
        preencher_dados_fixos(campos)

        print('\nIniciando processo...')
        for i in range(inicio, fim + 1):
            numero = f'{i:06}'

            tentativa = 1
            sucesso = False

            while tentativa <= MAX_TENTATIVAS and not sucesso:
                if tentativa > 1:
                    print(f'Tentando novamente o número: {numero}')
                else:
                    print(f'\nConsultando: {numero}')

                try:
                    campos['numero'].set_text(numero)
                    sleep(0.5)

                    send_keys(ATALHOS['consultar'])
                    sleep(3.5)

                    print('Imprimindo')
                    send_keys(ATALHOS['imprimir'])

                    handle_mini_menu(app)
                    sleep(0.5)

                    sucesso = handle_menu_impressao(app)
                    sleep(0.5)

                    if not sucesso:
                        raise RuntimeError('Alerta: Falha no fluxo.')

                except Exception as erro_tentativa:
                    tentativa += 1
                    fecha_menu_impressao(app)


    except Exception as e:
        print(f'\nERRO: {e}')
    finally:
        elapsed_time = perf_counter() - start_time
        print(f'\nTerminado em {elapsed_time:0.2f} segundos')
        input('Pressione Enter para fechar...')



if __name__ == '__main__':
    main()

