from time import sleep, perf_counter

from sincronizar_estatisticas import Sincronizador

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
from src.impressoras import Impressoras

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
        ) from e


def processar_lote(app, campos, lote, diario=None, execucao=None, *, impressora, ao_enviar=None):
    diario = diario if diario is not None else DiarioImpressao()
    execucao = execucao or diario.iniciar([lote], impressora)
    setor = lote['setor']
    preencher_dados_fixos(campos, setor)

    print(f'\nIniciando setor {setor}: {len(lote["ordens"])} ordens.')

    for numero in lote['ordens']:
        diario.atualizar(execucao, numero, setor, 'envio_iniciado')
        try:
            processar_ordem(app, campos, numero, impressora=impressora)
            diario.atualizar(execucao, numero, setor, 'concluido')
        except Exception:
            diario.interromper(execucao)
            raise
        if ao_enviar is not None:
            ao_enviar()

    print(f'Setor {setor} concluído.')


def main():
    with Sincronizador(aplicacao='impressao-ops'):
        return executar_console_impressao()


def executar_console_impressao():
    start_time = perf_counter()

    try:
        lotes = obter_lotes(MODO_ENTRADA)

        if not lotes:
            print('Nenhuma ondem informada.')
            return 0

        impressoras = Impressoras()
        if impressoras.aviso_preferencia:
            print(f'Aviso: {impressoras.aviso_preferencia}')
        impressora = impressoras.validar(impressoras.selecionada)
        print(f'Impressora do lote: {impressora}')

        uso_registrado = False
        def registrar_primeiro_uso():
            nonlocal uso_registrado
            if not uso_registrado:
                uso_registrado = True
                impressoras.registrar_uso(impressora)
                if impressoras.aviso_preferencia:
                    print(f'Aviso: {impressoras.aviso_preferencia}')

        diario = DiarioImpressao()
        execucao = diario.iniciar(lotes, impressora)
        app, campos = inicia_app()

        for lote in lotes:
            processar_lote(app, campos, lote, diario, execucao,
                          impressora=impressora, ao_enviar=registrar_primeiro_uso)
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
