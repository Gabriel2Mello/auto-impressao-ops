"""Localização atual das OPs por saldo em aberto, em transação somente leitura."""

import json
import os
from pathlib import Path
import sys


class ErroConsultaSisplan(RuntimeError):
    pass


def conectar_configurado():
    try:
        from pg8000.dbapi import connect

        raiz = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        arquivo = Path(os.environ.get('NUNES_BANCO_CONFIG') or
                       raiz.parent / 'estrutura-nunes' / 'area-nunes' / 'privado' / 'banco-sisplan.json')
        perfil = os.environ.get('NUNES_BANCO_PERFIL', 'principal')
        valores = json.loads(arquivo.read_text(encoding='utf-8'))['perfis'][perfil]
        if not all(isinstance(valores[chave], str) and valores[chave].strip()
                   for chave in ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')):
            raise ValueError('Configuração incompleta')
        porta = int(valores['PGPORT'])
        if not 1 <= porta <= 65535:
            raise ValueError('Porta inválida')
        return connect(host=valores['PGHOST'], port=porta, database=valores['PGDATABASE'],
                       user=valores['PGUSER'], password=valores['PGPASSWORD'], timeout=10,
                       application_name='impressao_ops_leitura')
    except Exception:
        # Nunca propagar mensagens de driver ou configuração com dados privados.
        raise ErroConsultaSisplan('Banco Sisplan indisponível. Confira a configuração local e as permissões de leitura.') from None


def consultar_localizacoes(lotes, conectar=conectar_configurado):
    numeros = list(dict.fromkeys(numero for lote in lotes for numero in lote['ordens']))
    conexao, cursor = None, None
    try:
        conexao = conectar()
        cursor = conexao.cursor()
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cursor.execute("SET LOCAL statement_timeout = '8000ms'")
        cursor.execute("SET LOCAL lock_timeout = '1500ms'")
        # O saldo é calculado por cor/tamanho, antes de agrupar: uma linha já
        # baixada não pode anular o saldo de outra linha da mesma OP.
        marcadores = ','.join(['%s'] * len(numeros))
        cursor.execute(f'''SELECT DISTINCT f.numero, f.codcli, f.op, e.nome, s.descricao
            FROM sisplan.faccao_001 f
            LEFT JOIN sisplan.entidade_001 e ON e.codcli = f.codcli
            LEFT JOIN sisplan.cadfluxo_001 s ON s.codigo = f.op
            WHERE f.numero IN ({marcadores})
              AND COALESCE(f.qt_orig, 0) - COALESCE(f.quant, 0)
                  - COALESCE(f.quant_2, 0) - COALESCE(f.quant_i, 0)
                  - COALESCE(f.quant_f, 0) > 0
            ORDER BY f.numero, f.codcli, f.op''', tuple(numeros))
        linhas = cursor.fetchall()
    except ErroConsultaSisplan:
        raise
    except Exception:
        raise ErroConsultaSisplan('Não foi possível consultar as OPs no Sisplan. Nenhuma impressão foi iniciada.') from None
    finally:
        if conexao is not None:
            falha = False
            for fechar in (conexao.rollback, cursor.close if cursor is not None else None, conexao.close):
                if fechar is not None:
                    try:
                        fechar()
                    except Exception:
                        falha = True
            if falha:
                raise ErroConsultaSisplan('Falha ao encerrar a leitura do Sisplan. Confira a conexão antes de tentar novamente.') from None

    por_numero = {numero: {} for numero in numeros}
    for numero, faccao, setor, nome, descricao in linhas:
        numero = str(numero).strip()
        faccao = str(faccao).strip() if faccao is not None else ''
        setor = str(setor).strip() if setor is not None else ''
        # Etiquetas acompanham a OP, mas não representam sua localização produtiva.
        if setor == '11':
            continue
        if (numero not in por_numero or not faccao.isascii() or not faccao.isdigit()
                or len(faccao) > 6 or not setor.isascii() or not setor.isdigit() or len(setor) > 6):
            raise ErroConsultaSisplan(f'OP {numero}: facção ou setor inválido no Sisplan. Confira o cadastro.')
        por_numero[numero][(faccao, setor)] = (str(nome or '').strip(), str(descricao or '').strip())

    grupos = {}
    for numero, locais in por_numero.items():
        if not locais:
            raise ErroConsultaSisplan(f'OP {numero}: não encontrada com saldo em aberto no Sisplan. Confira o número e a situação da OP.')
        if len(locais) != 1:
            detalhes = '; '.join(f'facção {f} / setor {s}' for f, s in locais)
            raise ErroConsultaSisplan(f'OP {numero}: mais de uma localização atual ({detalhes}). Confira a OP antes de imprimir.')
        (faccao, setor), (nome, descricao) = next(iter(locais.items()))
        grupo = grupos.setdefault((faccao, setor), dict(faccao=faccao, faccao_nome=nome,
                                  setor=setor, setor_nome=descricao, ordens=[]))
        grupo['ordens'].append(numero)
    return list(grupos.values())
