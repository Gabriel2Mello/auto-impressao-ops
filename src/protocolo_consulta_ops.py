"""Contrato da consulta de localização de OPs. Fonte no nunes-api-sisplan."""

from re import fullmatch

MAX_ORDENS = 5000
ROTA_CONSULTA = '/impressao-ops/v1/localizacoes'
LIMITE_PEDIDO = 128 * 1024
LIMITE_RESPOSTA = 2 * 1024 * 1024


class ErroConsultaSisplan(RuntimeError):
    pass


def numeros_dos_lotes(lotes):
    return list(dict.fromkeys(numero for lote in lotes for numero in lote['ordens']))


def pedido_valido(numero):
    return isinstance(numero, str) and len(numero) <= 50 and bool(fullmatch(r'[0-9]{4}-[0-9]{4,}', numero))


def validar_ordens(ordens):
    if not isinstance(ordens, list) or not 1 <= len(ordens) <= MAX_ORDENS:
        raise ValueError(f'Informe de 1 a {MAX_ORDENS} OPs.')
    if any(not isinstance(numero, str) or len(numero) < 6 or not numero.isascii()
           or not numero.isdigit() or (len(numero) > 6 and numero.startswith('0'))
           for numero in ordens):
        raise ValueError('Informe números de OP normalizados.')
    if len(set(ordens)) != len(ordens):
        raise ValueError('A lista contém OPs repetidas.')


def validar_pedidos(pedidos):
    if (not isinstance(pedidos, list) or not 1 <= len(pedidos) <= MAX_ORDENS
            or not all(pedido_valido(pedido) for pedido in pedidos)
            or len(set(pedidos)) != len(pedidos)):
        raise ValueError('Informe uma lista de pedidos normalizados, sem repetições.')
