"""Diário local: persistir antes de enviar e exigir conferência do resultado incerto."""

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from metricas_nunes import registrar_evento


class DiarioImpressao:
    def __init__(self, caminho=None):
        if caminho is not None:
            self.caminho = Path(caminho)
        else:
            base = Path(os.environ.get('NUNES_OPS_DADOS') or
                        Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') /
                        'Nunes' / 'ImpressaoOPs')
            self.caminho = base / 'execucoes.sqlite3'
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.conectar() as banco:
            versao = banco.execute('PRAGMA user_version').fetchone()[0]
            tabelas = banco.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if versao == 0 and not tabelas:
                banco.execute("""CREATE TABLE envios (
                    id TEXT PRIMARY KEY, execucao TEXT NOT NULL, numero TEXT NOT NULL,
                    setor TEXT NOT NULL, impressora TEXT NOT NULL, atualizado_em TEXT NOT NULL,
                    situacao TEXT NOT NULL CHECK(situacao IN (
                        'pendente','envio_iniciado','concluido','incerto',
                        'conferido_enviado','conferido_nao_enviado')),
                    UNIQUE(execucao, numero, setor))""")
                banco.execute('PRAGMA user_version=1')
            elif versao not in (1, 2):
                raise RuntimeError('Versão desconhecida do diário de impressão. Preserve o arquivo para análise.')
            if versao in (0, 1):
                # Apenas novas conclusões entram na fila; o histórico v1 já alimentou
                # métricas por OP/setor e não permite reconstruir todas as repetições.
                banco.execute('CREATE TABLE metricas (envio_id TEXT PRIMARY KEY REFERENCES envios(id))')
                banco.execute('PRAGMA user_version=2')
            invalidos = banco.execute("""SELECT COUNT(*) FROM envios WHERE situacao NOT IN
                ('pendente','envio_iniciado','concluido','incerto',
                 'conferido_enviado','conferido_nao_enviado')""").fetchone()[0]
            if invalidos:
                raise RuntimeError('Diário de impressão inválido. Preserve o arquivo para análise.')
        self.publicar_metricas()

    @contextmanager
    def conectar(self):
        banco = None
        try:
            banco = sqlite3.connect(self.caminho, timeout=5)
            banco.row_factory = sqlite3.Row
            banco.execute('PRAGMA synchronous=FULL')
            with banco:
                banco.execute('BEGIN IMMEDIATE')
                yield banco
        except (OSError, sqlite3.Error) as erro:
            raise RuntimeError('Não foi possível persistir ou ler o diário de impressão. '
                               'Nenhum envio pode ser repetido sem conferir a fila e o papel.') from erro
        finally:
            if banco is not None:
                banco.close()

    def consultar(self):
        with self.conectar() as banco:
            # O último lote inteiro e todas as incertezas anteriores continuam visíveis.
            ultima = banco.execute('SELECT execucao FROM envios ORDER BY rowid DESC LIMIT 1').fetchone()
            if ultima is None:
                return []
            return [dict(linha) for linha in banco.execute("""SELECT * FROM envios
                WHERE execucao=? OR situacao IN ('envio_iniciado','incerto') ORDER BY rowid""", (ultima[0],))]

    def iniciar(self, lotes, impressora=''):
        execucao = uuid4().hex
        with self.conectar() as banco:
            if banco.execute("SELECT 1 FROM envios WHERE situacao IN ('envio_iniciado','incerto') LIMIT 1").fetchone():
                raise RuntimeError('Existe impressão incerta. Confira a fila e o papel e registre a conferência antes de iniciar outro lote.')
            for lote in lotes:
                for numero in lote['ordens']:
                    banco.execute('INSERT OR IGNORE INTO envios VALUES (?,?,?,?,?,?,?)',
                                  (uuid4().hex, execucao, str(numero).zfill(6), str(lote['setor']),
                                   impressora or '', datetime.now(timezone.utc).isoformat(), 'pendente'))
        return execucao

    def atualizar(self, execucao, numero, setor, situacao):
        anterior = {'envio_iniciado': 'pendente', 'concluido': 'envio_iniciado'}[situacao]
        with self.conectar() as banco:
            cursor = banco.execute('UPDATE envios SET situacao=?, atualizado_em=? '
                                   'WHERE execucao=? AND numero=? AND setor=? AND situacao=?',
                                   (situacao, datetime.now(timezone.utc).isoformat(), execucao,
                                    str(numero).zfill(6), str(setor), anterior))
            if cursor.rowcount != 1:
                raise RuntimeError('Transição inválida no diário de impressão. Execução interrompida.')
            if situacao == 'concluido':
                banco.execute('INSERT INTO metricas SELECT id FROM envios '
                              'WHERE execucao=? AND numero=? AND setor=?',
                              (execucao, str(numero).zfill(6), str(setor)))
        if situacao == 'concluido':
            self.publicar_metricas()

    def publicar_metricas(self):
        """Republicar estatísticas pendentes nunca repete a operação de impressão."""
        try:
            with self.conectar() as banco:
                pendentes = banco.execute('SELECT envios.* FROM metricas JOIN envios '
                                         'ON envios.id=metricas.envio_id ORDER BY envios.rowid').fetchall()
            for envio in pendentes:
                aceito = registrar_evento('op_enviada', 'impressao:' + envio['id'], envio['numero'],
                                          empresa='FILIAL', setor=envio['setor'], execucao=envio['execucao'],
                                          ocorrido_em=datetime.fromisoformat(envio['atualizado_em']))
                if not aceito:
                    return
                with self.conectar() as banco:
                    banco.execute('DELETE FROM metricas WHERE envio_id=?', (envio['id'],))
        except (OSError, RuntimeError, ValueError):
            logging.exception('Estatística de impressão pendente no diário; será republicada ao reabrir '
                              'ou concluir outra OP. Nenhuma impressão será repetida.')

    def interromper(self, execucao):
        with self.conectar() as banco:
            banco.execute("UPDATE envios SET situacao='incerto', atualizado_em=? "
                          "WHERE execucao=? AND situacao='envio_iniciado'",
                          (datetime.now(timezone.utc).isoformat(), execucao))

    def conferir(self, identificador, resultado):
        if resultado not in ('conferido_enviado', 'conferido_nao_enviado'):
            raise ValueError('Informe se o envio foi confirmado ou se não houve envio após conferir a fila e o papel.')
        with self.conectar() as banco:
            cursor = banco.execute("UPDATE envios SET situacao=?, atualizado_em=? WHERE id=? "
                                   "AND situacao IN ('envio_iniciado','incerto')",
                                   (resultado, datetime.now(timezone.utc).isoformat(), identificador))
            if cursor.rowcount != 1:
                raise ValueError('Impressão incerta não encontrada ou já conferida. Atualize o painel.')
