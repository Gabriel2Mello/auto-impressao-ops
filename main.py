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

MODO_ENTRADA = 'arquivo' # 'arquivo', 'intervalos'
ARQUIVO_ORDENS = Path(__file__).resolve().parent / 'ordem_producao.txt'
MAX_TENTATIVAS = 2
MIN_SLEEP_SECONDS = 1


def normalizar_ordem(valor):
    texto = str(valor).strip()
    if not texto.isdigit():
        raise ValueError(f'Ordem de produção inválida: {valor!r}.')
    return f'{int(texto):06d}'


def coletar_intervalos():
    lotes = []

    while True:
        try:
            inicio_str = input('De:  ').strip()
            fim_str    = input('Até: ').strip() or inicio_str
            setor      = input('Setor: ').strip() or '10'

            inicio, fim = int(inicio_str), int(fim_str)

            if inicio > fim:
                print('\nErro: Número inicial maior que o final.')
                continue

            ordens = [normalizar_ordem(numero) for numero in range (inicio, fim + 1)]
            lotes.append({'setor': setor, 'ordens': ordens})

            continuar = input("Adicionar outro intervalo? (s/N): ").strip().lower()
            if continuar.upper() == 'N':
                break

            print()

        except ValueError as e:
            print(f"\nErro: {e}")

    return lotes


def ler_ordens_do_arquivo(caminho=ARQUIVO_ORDENS):
    if not caminho.exists():
        raise RuntimeError('Erro: Arquivo de ordens de produção não encontrado.')

    valores = caminho.read_text(encoding='utf-8').split()
    if not valores:
        raise RuntimeError(f'O arquivo está vazio: {caminho}')

    try:
        return list(dict.fromkeys(normalizar_ordem(valor) for valor in valores))
    except ValueError as e:
        raise RuntimeError(
            f'Erro ao ler arquivo ordem_producao.txt: {e}'
        ) from e


def coletar_arquivo():
    return [{
        'setor': input('Setor: ').strip() or '10',
        'ordens': ler_ordens_do_arquivo(),
    }]


def obter_lotes(modo):
    coletores = {
        'intervalos': coletar_intervalos,
        'arquivo': coletar_arquivo,
    }

    try:
        return coletores[modo.lower()]()
    except KeyError as e:
        raise RuntimeError(f'Modo de entrada inválido: {modo}') from e


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

