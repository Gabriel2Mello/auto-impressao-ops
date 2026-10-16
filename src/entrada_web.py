"""Validação das entradas do painel, sem acessar Sisplan ou impressora."""

from src.utils import normalizar_ordem

MAX_ORDENS = 5000


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
            lotes.append({'setor': setor_valido(intervalo), 'ordens': [
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
        lotes.append({'setor': setor_valido(dados), 'ordens': [
            normalizar_ordem(valor) for valor in valores
        ]})
    else:
        raise ValueError('Escolha De / Para ou Lista de OPs.')

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
