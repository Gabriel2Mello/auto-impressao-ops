from time import sleep, perf_counter

from pywinauto.keyboard import send_keys

from src.handle_app import (
    fecha_menu_impressao,
    inicia_app,
    ATALHOS,
    preencher_dados_fixos,
    handle_mini_menu,
    handle_menu_impressao
)


def input_numeros():
    while True:
        try:
            inicio_str = input('De:  ').strip()
            fim_str    = input('Até: ' ).strip()
            setor      = input('Setor: ').strip()

            inicio, fim = int(inicio_str), int(fim_str)

            if inicio >= fim:
                print('\nErro: Número inicial maior que o final.')
                pass

            return inicio, fim, setor
        except ValueError:
            print("\nErro: Digite apenas números.")


def main():
    inicio, fim, setor = input_numeros()
    if not all([inicio, fim, setor]):
        input('Pressione Enter para Fechar...')
        return

    start_time = perf_counter()
    MAX_TENTATIVAS = 2
    DELAY_CONSULTA = 3.5
    DELAY_MINIMO = 0.5

    try:
        app, campos = inicia_app()
        preencher_dados_fixos(campos, setor)

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
                    sleep(DELAY_MINIMO)

                    send_keys(ATALHOS['consultar'])
                    sleep(DELAY_CONSULTA)

                    print('Imprimindo')
                    send_keys(ATALHOS['imprimir'])

                    handle_mini_menu(app)
                    sleep(DELAY_MINIMO)

                    sucesso = handle_menu_impressao(app)
                    sleep(DELAY_MINIMO)

                    if not sucesso:
                        raise RuntimeError('Alerta: Falha no fluxo.')

                except Exception:
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

