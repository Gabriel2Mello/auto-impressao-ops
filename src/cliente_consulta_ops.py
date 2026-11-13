"""Consulta autenticada com a identidade da sessão Windows, via WinHTTP."""

import json
import os

from src.protocolo_consulta_ops import (
    ErroConsultaSisplan, LIMITE_PEDIDO, LIMITE_RESPOSTA, ROTA_CONSULTA,
    numeros_dos_lotes, validar_ordens, validar_pedidos,
)


def _postar(url, corpo):
    import pythoncom
    from win32com.client.dynamic import Dispatch

    pythoncom.CoInitialize()
    try:
        requisicao = Dispatch('WinHttp.WinHttpRequest.5.1')
        try:
            requisicao.Open('POST', url, True)
            requisicao.SetTimeouts(3000, 5000, 5000, 23000)
            requisicao.SetProxy(1)  # HTTPREQUEST_PROXYSETTING_DIRECT
            # Option é uma propriedade COM indexada.
            interface = requisicao._oleobj_
            try:
                opcao = interface.GetIDsOfNames('Option')
                for indice, valor in ((4, 0), (6, False)):  # SslErrorIgnoreFlags, EnableRedirects
                    interface.Invoke(opcao, 0, pythoncom.DISPATCH_PROPERTYPUT, False, indice, valor)
            finally:
                del interface
            # A URL é fixa no TS01 e o WinHTTP pode não classificar o FQDN como intranet.
            requisicao.SetAutoLogonPolicy(0)  # AutoLogonPolicy_Always
            requisicao.SetRequestHeader('Content-Type', 'application/json')
            requisicao.SetRequestHeader('Accept', 'application/json')
            requisicao.Send(corpo)
            # A consulta deve terminar antes do prazo de 30 s do painel.
            if not requisicao.WaitForResponse(24):
                requisicao.Abort()
                raise TimeoutError('Tempo limite da consulta no TS01.')
            status = requisicao.Status
            if status not in (200, 422):
                return status, b''
            tipo = requisicao.GetResponseHeader('Content-Type').split(';', 1)[0].strip().lower()
            if tipo != 'application/json':
                raise ValueError('Tipo de resposta inesperado.')
            return status, bytes(requisicao.ResponseBody)
        finally:
            del requisicao
    finally:
        pythoncom.CoUninitialize()


def _validar_localizacoes(lotes, numeros):
    if not isinstance(lotes, list) or not lotes:
        raise ValueError('Lotes inválidos.')
    ordens_recebidas = []
    locais = set()
    for lote in lotes:
        if (not isinstance(lote, dict)
                or lote.keys() != {'faccao', 'faccao_nome', 'setor', 'setor_nome', 'ordens'}):
            raise ValueError('Localização inválida.')
        codigos = (lote['faccao'], lote['setor'])
        if any(not isinstance(codigo, str) or not codigo.isascii() or not codigo.isdigit()
               or len(codigo) > 6 for codigo in codigos):
            raise ValueError('Código inválido.')
        if codigos in locais or lote['setor'] == '11':
            raise ValueError('Localização inesperada.')
        locais.add(codigos)
        if any(not isinstance(lote[chave], str) for chave in ('faccao_nome', 'setor_nome')):
            raise ValueError('Descrição inválida.')
        validar_ordens(lote['ordens'])
        ordens_recebidas.extend(lote['ordens'])
    validar_ordens(ordens_recebidas)
    if numeros is not None and set(ordens_recebidas) != set(numeros):
        raise ValueError('A resposta diverge das OPs consultadas.')
    return lotes


def consultar_localizacoes(lotes):
    numeros = numeros_dos_lotes(lotes)
    return _consultar({'ordens': numeros}, numeros)


def consultar_pedidos(pedidos):
    validar_pedidos(pedidos)
    return _consultar({'pedidos': pedidos})


def _consultar(entrada, numeros=None):
    porta = os.environ.get('NUNES_OPS_API_PORTA', '443')
    if not porta.isascii() or not porta.isdigit() or len(porta) > 5 or not 1 <= int(porta) <= 65535:
        raise ErroConsultaSisplan('Porta da consulta no TS01 inválida. Confira NUNES_OPS_API_PORTA.')
    url = f'https://ts01.gratitude.local:{int(porta)}{ROTA_CONSULTA}'
    corpo = json.dumps(entrada, separators=(',', ':')).encode('ascii')
    if len(corpo) > LIMITE_PEDIDO:
        raise ErroConsultaSisplan('A lista excede o tamanho aceito pela consulta.')
    try:
        status, resposta = _postar(url, corpo)
        if status in (401, 403):
            raise ErroConsultaSisplan('A conta Windows desta sessão não tem acesso à consulta no TS01.')
        if status not in (200, 422) or len(resposta) > LIMITE_RESPOSTA:
            raise ValueError('Resposta inesperada.')
        dados = json.loads(resposta.decode('utf-8'))
        if not isinstance(dados, dict):
            raise ValueError('Resposta inválida.')
        if status == 422:
            mensagem = dados.get('erro')
            if not isinstance(mensagem, str) or not mensagem:
                raise ValueError('Erro inválido.')
            raise ErroConsultaSisplan(mensagem)
        return _validar_localizacoes(dados.get('lotes'), numeros)
    except ErroConsultaSisplan:
        raise
    except Exception:
        raise ErroConsultaSisplan('Consulta ao Sisplan indisponível no TS01. Confira a conexão e tente novamente.') from None
