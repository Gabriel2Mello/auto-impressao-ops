"""Preferência da conferência, independente da última impressora utilizada."""

from integracao_hub import gravar_registro, ler_registro


def ler_consulta(caminho):
    valor = ler_registro(caminho).get('consultar_sisplan')
    return valor if isinstance(valor, bool) else False


def salvar_consulta(caminho, valor):
    if not isinstance(valor, bool):
        raise ValueError('Opção de consulta ao Sisplan inválida.')
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        gravar_registro(caminho, {'consultar_sisplan': valor})
    except OSError:
        raise RuntimeError('Não foi possível salvar a opção Consultar no Sisplan. Verifique a permissão da pasta de configurações e tente novamente.') from None
