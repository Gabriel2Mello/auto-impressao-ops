"""Filas instaladas no Windows e preferência local de impressão do usuário."""

import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile


def listar_impressoras_windows():
    if sys.platform != 'win32':
        raise RuntimeError('A seleção de impressoras requer o Windows.')

    class PRINTER_INFO_4W(ctypes.Structure):
        _fields_ = [('pPrinterName', wintypes.LPWSTR),
                    ('pServerName', wintypes.LPWSTR), ('Attributes', wintypes.DWORD)]

    try:
        enumerar = ctypes.WinDLL('winspool.drv', use_last_error=True).EnumPrintersW
        enumerar.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        enumerar.restype = wintypes.BOOL
        tamanho, quantidade = wintypes.DWORD(), wintypes.DWORD()
        # LOCAL | CONNECTIONS, nível 4: consulta o cache local, sem abrir cada fila remota.
        if enumerar(6, None, 4, None, 0, ctypes.byref(tamanho), ctypes.byref(quantidade)):
            return []
        erro = ctypes.get_last_error()
        if erro != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise ctypes.WinError(erro)
        # O conjunto de filas pode mudar entre a consulta do tamanho e a leitura.
        for _ in range(3):
            buffer = ctypes.create_string_buffer(tamanho.value)
            if enumerar(6, None, 4, buffer, len(buffer), ctypes.byref(tamanho), ctypes.byref(quantidade)):
                filas = ctypes.cast(buffer, ctypes.POINTER(PRINTER_INFO_4W))
                return sorted({filas[i].pPrinterName for i in range(quantidade.value)
                               if filas[i].pPrinterName}, key=str.casefold)
            erro = ctypes.get_last_error()
            if erro != 122:
                raise ctypes.WinError(erro)
        raise RuntimeError('A lista de impressoras mudou durante a consulta. Atualize a lista.')
    except OSError as erro:
        logging.exception('Falha ao consultar impressoras do Windows')
        raise RuntimeError('Não foi possível listar as impressoras. Verifique o serviço de impressão do Windows e atualize a lista.') from erro


def caminho_preferencia():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    return base / 'Nunes' / 'ImpressaoOPs' / 'config.json'


class Impressoras:
    def __init__(self, caminho=None, listar=None):
        self.caminho = Path(caminho) if caminho is not None else caminho_preferencia()
        self.listar = listar if listar is not None else listar_impressoras_windows
        self.nomes = []
        self.aviso = ''
        self.aviso_preferencia = ''
        self.selecionada = self._carregar() or os.environ.get('IMPRESSORA_OP', '').strip().strip('"')
        self.atualizar()

    def _carregar(self):
        try:
            dados = json.loads(self.caminho.read_text(encoding='utf-8'))
            nome = dados['ultima_impressora']
            if not isinstance(nome, str) or not nome.strip():
                raise ValueError('Nome de impressora inválido.')
            return nome
        except FileNotFoundError:
            return ''
        except (OSError, ValueError, KeyError, TypeError):
            logging.warning('Não foi possível ler a preferência de impressora', exc_info=True)
            self.aviso_preferencia = 'Não foi possível ler a última impressora utilizada. Selecione a impressora novamente.'
            return ''

    def atualizar(self):
        try:
            self.nomes = sorted(set(self.listar()), key=str.casefold)
        except RuntimeError as erro:
            self.nomes = []
            self.aviso = str(erro)
        else:
            if self.selecionada and self.selecionada not in self.nomes:
                self.aviso = f'A impressora “{self.selecionada}” não está instalada ou foi renomeada. Selecione outra impressora.'
            else:
                self.aviso = '' if self.nomes else 'Nenhuma impressora instalada foi encontrada. Instale uma impressora no Windows e atualize a lista.'
        return self.situacao()

    def situacao(self):
        return {'impressora': self.selecionada if self.selecionada in self.nomes else '',
                'aviso_impressora': self.aviso or self.aviso_preferencia}

    def selecionar(self, nome):
        self.atualizar()
        if not isinstance(nome, str) or nome not in self.nomes:
            raise ValueError(self.aviso or 'Selecione uma impressora instalada neste computador.')
        self.selecionada = nome
        self.aviso = ''

    def validar(self, nome):
        self.atualizar()
        if not isinstance(nome, str) or not nome or nome not in self.nomes:
            raise RuntimeError(self.aviso or 'Selecione uma impressora instalada antes de imprimir.')
        return nome

    def registrar_uso(self, nome):
        temporario = None
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.caminho.parent,
                                    suffix='.tmp', delete=False) as arquivo:
                temporario = Path(arquivo.name)
                json.dump({'ultima_impressora': nome}, arquivo, ensure_ascii=False)
                arquivo.write('\n')
            os.replace(temporario, self.caminho)
            self.aviso_preferencia = ''
        except OSError:
            logging.exception('Falha ao salvar a última impressora utilizada')
            self.aviso_preferencia = 'A impressão continua, mas não foi possível lembrar a impressora. Verifique a permissão da pasta de configurações.'
        finally:
            if temporario is not None:
                try:
                    temporario.unlink(missing_ok=True)
                except OSError:
                    logging.warning('Não foi possível remover o arquivo temporário de preferência')
