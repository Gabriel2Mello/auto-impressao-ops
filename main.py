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

MAX_TENTATIVAS = 2
DELAY_CONSULTA = 3.5
DELAY_MINIMO = 0.5
RETRY_PAUSE_SECONDS = 1

def coletar_intervalos():
    intervalos = []
    while True:
        try:
            inicio_str = input('De:  ').strip()
            fim_str    = input('Até: ').strip()
            setor      = input('Setor: ').strip()

            if fim_str == '':
                fim_str = inicio_str

            inicio, fim = int(inicio_str), int(fim_str)

            if inicio > fim:
                print('\nErro: Número inicial maior que o final.')
                continue

            intervalos.append({'inicio': inicio, 'fim': fim, 'setor': setor})

            continuar = input("Adicionar outro intervalo? (s/N): ").strip().lower()
            if continuar != 's':
                break

        except ValueError:
            print("\nErro: Digite apenas números.")
        except Exception as e:
            print(f"\nErro inesperado durante a entrada: {e}")
            break

    return intervalos


def processar_intervalo(app, campos, inicio, fim, setor):
    preencher_dados_fixos(campos, setor)

    print('\nIniciando processo para o setor:', setor)
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
                    raise RuntimeError('Alerta: Falha no fluxo de impressão.')

            except Exception as e:
                print(f"Erro processando {numero}: {e}")
                tentativa += 1
                fecha_menu_impressao(app)
                sleep(RETRY_PAUSE_SECONDS)

    print(f'Intervalo concluído.')


def main():
    intervalos = coletar_intervalos()
    if not intervalos:
        input('Pressione Enter para Fechar...')
        return

    start_time = perf_counter()

    try:
        app, campos = inicia_app()

        for intervalo in intervalos:
            inicio = intervalo['inicio']
            fim    = intervalo['fim']
            setor  = intervalo['setor']

            processar_intervalo(app, campos, inicio, fim, setor)

    except Exception as e:
        print(f'\nERRO: {e}')
    finally:
        elapsed_time = perf_counter() - start_time
        print(f'\nTerminado em {elapsed_time:0.2f} segundos')
        input('Pressione Enter para fechar...')


if __name__ == '__main__':
    main()

