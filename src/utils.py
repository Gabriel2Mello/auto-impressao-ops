from pathlib import Path

ARQUIVO_ORDENS = Path(__file__).resolve().parent.parent / 'ordem_producao.txt'


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


def normalizar_ordem(valor):
    texto = str(valor).strip()
    if not texto.isdigit():
        raise ValueError(f'Ordem de produção inválida: {valor!r}.')
    return f'{int(texto):06d}'


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

