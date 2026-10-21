"""Consulta e conferência local, sem enviar OPs ao Sisplan ou à impressora."""
import argparse
import json

from src.diario_impressao import DiarioImpressao


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', help='Identificador da impressão incerta exibido na consulta')
    parser.add_argument('--resultado', choices=('conferido_enviado', 'conferido_nao_enviado'))
    parser.add_argument('--conferi-fila-e-papel', action='store_true')
    args = parser.parse_args()
    diario = DiarioImpressao()
    if args.id or args.resultado or args.conferi_fila_e_papel:
        if not (args.id and args.resultado and args.conferi_fila_e_papel):
            parser.error('Informe --id, --resultado e --conferi-fila-e-papel juntos.')
        diario.conferir(args.id, args.resultado)
    print(json.dumps(diario.consultar(), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    from integracao_hub import executar_console
    raise SystemExit(executar_console('impressao-ops', 'Conferência de impressão de OPs', main))
