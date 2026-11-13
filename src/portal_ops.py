"""Configuração e rotas privadas entre IIS e o executor de Impressão de OPs."""

from dataclasses import dataclass
import json
import re


GET_PAINEL = frozenset({
    '/', '/impressao.css', '/impressao.js', '/nunes-tema.js', '/rolagem.js',
    '/icons/tema-lua.svg', '/icons/tema-lua-sol.svg', '/icons/icone.svg',
    '/favicon.ico', '/icons/icone-192.png', '/api/estado', '/api/impressoras',
})
POST_PAINEL = frozenset({
    '/api/conferir', '/api/iniciar', '/api/conferir-impressao',
    '/api/impressora', '/api/preferencia-consulta', '/api/parar',
})
CAMINHO_TS01 = '/impressao-ops'
ORIGEM_TS01 = 'https://ts01'
LIMITE_CORPO = 100000
LIMITE_RESPOSTA = 4 * 1024 * 1024
SEGREDO_HEX = re.compile(r'[0-9a-f]{64}')
TOKEN_PAINEL = re.compile(r'[A-Za-z0-9_-]{43}')


@dataclass(frozen=True)
class ConfigPortal:
    origem: str
    porta_executor: int
    porta_api: int
    segredo: str


def ler_config_portal(arquivo):
    dados = json.loads(arquivo.read_text(encoding='utf-8'))
    if not isinstance(dados, dict):
        raise ValueError('Configuração do portal inválida.')
    origem = dados.get('origem')
    porta_executor = dados.get('porta_executor')
    porta_api = dados.get('porta_api')
    segredo = dados.get('segredo')
    origem_legada = isinstance(origem, str) and re.fullmatch(
        r'https://ts01\.gratitude\.local:([1-9][0-9]{0,4})', origem,
    )
    porta_portal = 443 if origem == ORIGEM_TS01 else int(origem_legada[1]) if origem_legada else 0
    if (type(porta_executor) is not int or type(porta_api) is not int
            or not 1024 <= porta_executor <= 65535 or not 1024 <= porta_api <= 65535
            or not 1 <= porta_portal <= 65535
            or (porta_portal != 443 and porta_portal < 1024)
            or len({porta_executor, porta_api, porta_portal}) != 3
            or not isinstance(segredo, str) or not SEGREDO_HEX.fullmatch(segredo)):
        raise ValueError('Confira a origem HTTPS, as três portas e o segredo do portal.')
    return ConfigPortal(origem, porta_executor, porta_api, segredo)
