"""Validação das entradas do painel, sem acessar Sisplan ou impressora."""

from datetime import date
from re import fullmatch, split

from src.protocolo_consulta_ops import MAX_ORDENS, pedido_valido
from src.utils import normalizar_ordem

MAX_TEXTO_PEDIDOS = 60000


def analisar_pedidos(dados):
    conteudo = texto(dados, 'pedidos')
    if len(conteudo) > MAX_TEXTO_PEDIDOS:
        raise ValueError('A lista de pedidos é muito grande.')
    ano = date.today().year
    pedidos, invalidos = {}, []
    for parte in split(r'[,\r\n]', conteudo):
        numero = parte.strip()
        if not numero:
            continue
        pedido = f'{ano}-{numero}' if fullmatch(r'[0-9]{4,}', numero) else numero
        if pedido_valido(pedido):
            pedidos[pedido] = None
        else:
            invalidos.append(numero)
    if invalidos:
        raise ValueError('Confira estes números de pedido: ' + ', '.join(invalidos)[:400] + '.')
    if not pedidos:
        raise ValueError('Informe pelo menos um pedido.')
    if len(pedidos) > MAX_ORDENS:
        raise ValueError(f'O limite por execução é de {MAX_ORDENS} pedidos.')
    if sum(len(pedido) + 1 for pedido in pedidos) - 1 > MAX_TEXTO_PEDIDOS:
        raise ValueError('A lista de pedidos é muito grande depois de completar os anos. Divida os pedidos em lotes menores.')
    return list(pedidos)


def texto(dados, chave, padrao=''):
    valor = dados.get(chave, padrao)
    if not isinstance(valor, str):
        raise ValueError(f'Campo {chave} inválido.')
    return valor.strip()


def setor_valido(dados):
    setor = texto(dados, 'setor') or '10'
    if not setor.isascii() or not setor.isdigit() or len(setor) > 6:
        raise ValueError('Informe um setor numérico com até seis dígitos.')
    return setor


def montar_lotes(dados):
    if not isinstance(dados, dict):
        raise ValueError('Entrada inválida.')
    consultar = dados.get('consultar_sisplan', False)
    if not isinstance(consultar, bool):
        raise ValueError('Opção de consulta ao Sisplan inválida.')
    modo = texto(dados, 'modo')
    lotes = []
    if modo == 'intervalos':
        intervalos = dados.get('intervalos')
        if not isinstance(intervalos, list) or not 1 <= len(intervalos) <= 100:
            raise ValueError('Informe de 1 a 100 intervalos.')
        for intervalo in intervalos:
            if not isinstance(intervalo, dict):
                raise ValueError('Intervalo inválido.')
            inicio = normalizar_ordem(texto(intervalo, 'de'))
            fim = normalizar_ordem(texto(intervalo, 'para') or inicio)
            if int(inicio) > int(fim):
                raise ValueError('A OP inicial deve ser menor ou igual à final.')
            if int(fim) - int(inicio) + 1 > MAX_ORDENS:
                raise ValueError(f'O limite por execução é de {MAX_ORDENS} OPs.')
            lotes.append({'setor': '10' if consultar else setor_valido(intervalo), 'ordens': [
                normalizar_ordem(numero) for numero in range(int(inicio), int(fim) + 1)
            ]})
    elif modo == 'lista':
        conteudo = texto(dados, 'ordens')
        if len(conteudo) > 60000:
            raise ValueError('A lista é muito grande.')
        valores = conteudo.replace(',', ' ').replace(';', ' ').split()
        if not valores:
            raise ValueError('Informe pelo menos uma OP.')
        if len(valores) > MAX_ORDENS:
            raise ValueError(f'O limite por execução é de {MAX_ORDENS} OPs.')
        lotes.append({'setor': '10' if consultar else setor_valido(dados), 'ordens': [
            normalizar_ordem(valor) for valor in valores
        ]})
    else:
        raise ValueError('Escolha Por intervalo, Lista de OPs ou Pedido.')

    # Uma OP repetida no mesmo setor é enviada somente uma vez por execução.
    vistos = set()
    resultado = []
    for lote in lotes:
        ordens = []
        for numero in lote['ordens']:
            chave = (lote['setor'], numero)
            if chave not in vistos:
                vistos.add(chave)
                ordens.append(numero)
        if ordens:
            resultado.append({'setor': lote['setor'], 'ordens': ordens})
        if len(vistos) > MAX_ORDENS:
            raise ValueError(f'O limite por execução é de {MAX_ORDENS} OPs.')
    return resultado
