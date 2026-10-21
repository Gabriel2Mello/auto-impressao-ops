from time import sleep, perf_counter

from metricas_nunes import registrar_evento

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
from src.diario_impressao import DiarioImpressao

MIN_SLEEP_SECONDS = 1
MODO_ENTRADA = 'arquivo' # 'arquivo', 'intervalos'


def processar_ordem(app, campos, numero, impressora=None):
    print(f'\nConsultando: {numero}')

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

        if not handle_menu_impressao(app, impressora=impressora):
            raise RuntimeError('Falha no menu de impressão.')

        return True

    except Exception as e:
        fecha_menu_impressao(app)
        # O diálogo pode falhar depois do envio; a OP não deve ser repetida.
        raise RuntimeError(
            f'Falha no fluxo de impressão da OP {numero}: {e} '
            'Execução interrompida, sem repetição automática. '
            f'Confira a OP {numero} na fila da impressora e no papel '
            'antes de iniciar outra execução.'
        ) from e


def processar_lote(app, campos, lote, diario=None, execucao=None):
    diario = diario if diario is not None else DiarioImpressao()
    execucao = execucao or diario.iniciar([lote])
    setor = lote['setor']
    preencher_dados_fixos(campos, setor)

    print(f'\nIniciando setor {setor}: {len(lote["ordens"])} ordens.')

    for numero in lote['ordens']:
        diario.atualizar(execucao, numero, setor, 'envio_iniciado')
        try:
            processar_ordem(app, campos, numero)
            diario.atualizar(execucao, numero, setor, 'concluido')
        except Exception:
            diario.interromper(execucao)
            raise
        registrar_evento('op_enviada', f'{str(numero).zfill(6)}:{setor}', str(numero).zfill(6),
                         empresa='FILIAL', setor=str(setor))

    print(f'Setor {setor} concluído.')


def main():
    start_time = perf_counter()

    try:
        lotes = obter_lotes(MODO_ENTRADA)

        if not lotes:
            print('Nenhuma ondem informada.')
            return 0

        diario = DiarioImpressao()
        execucao = diario.iniciar(lotes)
        app, campos = inicia_app()

        for lote in lotes:
            processar_lote(app, campos, lote, diario, execucao)
        return 0

    except Exception as e:
        print(f'\nERRO: {e}')
        return 1
    finally:
        elapsed_time = perf_counter() - start_time

        print(f'\nTerminado em {elapsed_time:0.2f} segundos')
        input('Pressione Enter para fechar...')


if __name__ == '__main__':
    from integracao_hub import executar_console
    raise SystemExit(executar_console('impressao-ops', 'Impressão de OPs', main))

