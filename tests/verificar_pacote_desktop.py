"""Abre pacote ocioso com dados isolados; não prepara lotes nem imprime."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time

from integracao_hub import consultar_instancia, solicitar_encerramento


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    with TemporaryDirectory(prefix='nunes-impressao-pacote-') as pasta:
        raiz = Path(pasta)
        ambiente = dict(os.environ, LOCALAPPDATA=str(raiz / 'localappdata'),
                        NUNES_OPS_DADOS=str(raiz / 'ops'), NUNES_HUB_DADOS=str(raiz / 'hub'),
                        NUNES_METRICAS_DADOS=str(raiz / 'metricas'),
                        NUNES_CENTRAL_CONFIG=str(raiz / 'central-ausente.json'))
        processo = subprocess.Popen([str(exe)], cwd=exe.parent, env=ambiente)
        registro = None
        try:
            limite = time.monotonic() + 45
            while time.monotonic() < limite:
                if processo.poll() is not None:
                    raise RuntimeError(f'O pacote terminou antes de abrir: {processo.returncode}')
                try:
                    registro = json.loads((raiz / 'hub/impressao-ops.json').read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    time.sleep(.1)
                    continue
                saude = consultar_instancia(registro)
                if saude.get('respondendo') and registro.get('desktop') == 1 and saude.get('paginas', 0) > 0:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Pacote não confirmou desktop e página carregada no prazo.')
            # Uma nova abertura precisa ativar a mesma janela, sem segundo servidor.
            segunda = subprocess.run([str(exe)], cwd=exe.parent, env=ambiente, timeout=25)
            assert segunda.returncode == 0, 'Segunda abertura não ativou a instância'
            atual = json.loads((raiz / 'hub/impressao-ops.json').read_text(encoding='utf-8'))
            assert atual['pid'] == registro['pid'], 'Segunda abertura substituiu o processo'
            solicitar_encerramento(registro)
            assert processo.wait(timeout=25) == 0, 'Pacote encerrou com falha'
            print('Pacote: abriu WebView2, confirmou presença, reativou a mesma instância e encerrou pelo Hub. Nenhum lote preparado ou impresso.')
        finally:
            if processo.poll() is None and registro is not None:
                solicitar_encerramento(registro)
                processo.wait(timeout=25)


if __name__ == '__main__':
    main()
