"""Encaminha somente as rotas do portal autenticado pelo IIS."""

from hashlib import sha256
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import sys

from src.portal_ops import GET_PAINEL, LIMITE_CORPO, LIMITE_RESPOSTA, POST_PAINEL, TOKEN_PAINEL, ler_config_portal


def erro(status, mensagem):
    return status, [('Content-Type', 'application/json; charset=utf-8')], json.dumps(
        {'erro': mensagem}, ensure_ascii=False,
    ).encode('utf-8')


def atender(ambiente, entrada, config):
    usuario = ambiente.get('LOGON_USER', '')
    if (ambiente.get('HTTPS', '').lower() != 'on' or not usuario
            or ambiente.get('AUTH_TYPE', '').lower() not in {'negotiate', 'kerberos', 'ntlm'}
            or ambiente.get('HTTP_HOST', '').lower() != config.origem.removeprefix('https://')):
        return erro(403, 'Acesso ao portal não autorizado.')
    metodo = ambiente.get('REQUEST_METHOD', '')
    rota = ambiente.get('URL') or ambiente.get('SCRIPT_NAME', '')
    origem = ambiente.get('HTTP_ORIGIN')
    rotas = {'GET': GET_PAINEL, 'POST': POST_PAINEL}.get(metodo, ())
    if rota not in rotas or ambiente.get('QUERY_STRING'):
        return erro(404, 'Rota inexistente.')
    if origem not in ((config.origem,) if metodo == 'POST' else (None, config.origem)):
        return erro(403, 'Origem da solicitação não autorizada.')
    cabecalhos = {
        'X-Impressao-Portal': config.segredo,
        'X-Impressao-Operador': sha256(usuario.casefold().encode('utf-8')).hexdigest(),
    }
    if rota.startswith('/api/'):
        token = ambiente.get('HTTP_X_IMPRESSAO_TOKEN', '')
        if not TOKEN_PAINEL.fullmatch(token):
            return erro(403, 'Reabra o painel para acessar o portal.')
        cabecalhos['X-Impressao-Token'] = token
    if origem:
        cabecalhos['Origin'] = origem
    corpo = None
    if metodo == 'POST':
        tamanho = ambiente.get('CONTENT_LENGTH', '')
        tipo = ambiente.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower()
        if (not tamanho.isascii() or not tamanho.isdigit() or len(tamanho) > 6
                or not 1 <= int(tamanho) <= LIMITE_CORPO or tipo != 'application/json'):
            return erro(400, 'Solicitação inválida ou muito grande.')
        corpo = entrada.read(int(tamanho))
        if len(corpo) != int(tamanho):
            return erro(400, 'Solicitação incompleta.')
        cabecalhos['Content-Type'] = 'application/json'

    conexao = HTTPConnection('127.0.0.1', config.porta_executor, timeout=28)
    try:
        conexao.request(metodo, rota, corpo, cabecalhos)
        resposta = conexao.getresponse()
        conteudo = resposta.read(LIMITE_RESPOSTA + 1)
        if len(conteudo) > LIMITE_RESPOSTA:
            return erro(502, 'Resposta do executor excede o limite do portal.')
        campos = {'content-type', 'content-security-policy', 'referrer-policy'}
        return resposta.status, [(k, v) for k, v in resposta.getheaders() if k.lower() in campos], conteudo
    except (OSError, HTTPException):
        return erro(503, 'Executor indisponível no TS01. Confira o andamento antes de repetir.')
    finally:
        conexao.close()


def main():
    programa = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
    try:
        config = ler_config_portal(programa.parent.parent / 'privado' / 'portal.json')
        status, cabecalhos, corpo = atender(os.environ, sys.stdin.buffer, config)
    except Exception:
        status, cabecalhos, corpo = erro(503, 'Portal indisponível. Confira a configuração no TS01.')
    linhas = [f'Status: {status} {HTTPStatus(status).phrase}']
    linhas.extend(f'{nome}: {valor}' for nome, valor in cabecalhos)
    linhas.extend(('Cache-Control: no-store', 'X-Content-Type-Options: nosniff',
                   f'Content-Length: {len(corpo)}', '', ''))
    sys.stdout.buffer.write('\r\n'.join(linhas).encode('ascii') + corpo)


if __name__ == '__main__':
    main()
