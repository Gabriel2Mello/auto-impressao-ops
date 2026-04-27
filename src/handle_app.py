from pywinauto.application import Application
from pywinauto.keyboard import send_keys


CAMPOS = {
    'sisplan': 'Sisplan - 002 - NUNES ENXOVAIS IND, COM, IMP E EXP LTDA',
    'movimentacao': 0,
    'faccao': 4,
    'numero': 5,
    'setor': 7,
    'lancamento': 5,
    'saida': 0,
    'combo_parte': 3,
    'visualizar': 0,
    'nome_impressora': 5
}

ATALHOS = {
    'consultar': '%c',
    'imprimir': '%p',
    'ok': '%o'
}


def get_field_title(parent, class_name, title):
    return parent.child_window(
        class_name=class_name,
        title=title
    )


def get_field_index(parent, class_name, campo):
    index = CAMPOS.get(campo)
    if index is None:
        raise RuntimeError(f'Campo não mapeado: {campo}')

    return parent.child_window(
        class_name=class_name,
        found_index=index
    )


def mapear_campos(tab_envio):
    definicoes = {
        'numero':       ('TEdit', 'numero'),
        'setor':        ('TEdit', 'setor'),
        'movimentacao': ('TEdit', 'movimentacao'),
        'lancamento':   ('TCurrencyEdit', 'lancamento'),
        'saida':        ('TDateEditSisp', 'saida'),
        'combo_parte':  ('TComboBox', 'combo_parte'),
    }

    return {nome: get_field_index(tab_envio, classe, chave)
            for nome, (classe, chave) in definicoes.items()}


def preencher_dados_fixos(campos):
    dados = {
        'setor': '10',
        'movimentacao': '',
        'lancamento': 0,
        'saida': '  /  /    ',
    }

    for nome, valor in dados.items():
        campos[nome].set_text(valor)


def inicia_app():
    try:
        app = Application(backend='win32').connect(
            title=CAMPOS['sisplan'],
            class_name='TApplication',
            timeout=5
        )

        main_window = app.window(
            title=CAMPOS['sisplan'],
            class_name='TApplication'
        )
        main_window.restore().set_focus()

        janela_rel = app.window(
            title_re='.*RelFaccao01.*',
            class_name='TfmPrincipal'
        )
        janela_rel.wait('ready', timeout=5)

        tab_envio = get_field_title(
            janela_rel, 'TTabSheet', 'Envio'
        )

        campos = mapear_campos(tab_envio)

        return app, campos

    except Exception as e:
        raise RuntimeError(f'Erro ao conectar no Sisplan: {e}')


def handle_carrega_consulta(app):
    aviso = app.window(
        title='Aviso', class_name='TfmAviso'
    )

    existe = aviso.exists()
    if existe:
        try:
            aviso.wait_not('exists', timeout=5)
        except Exception:
            print('Aviso: Consulta demorou muito para sumir.')

    return existe


def handle_mini_menu(app):
    try:
        form_imprimir = app.window(
            title='Impressão', class_name='TForm'
        )
        form_imprimir.wait('visible', timeout=2)

        check_visualizar = get_field_title(
            form_imprimir, 'TCheckBox', 'Não visualizar.'
        )
        check_visualizar.check_by_click()

        send_keys(ATALHOS['ok'])

    except Exception as e:
        print(f'Aviso no mini menu: {e}')


def handle_menu_impressao(app):
    try:
        tela_impressao = app.window(
            class_name='TfrxPrintDialog'
        )
        tela_impressao.wait('ready', timeout=5)
        tela_impressao.set_focus()

        combo_nome_impressora = get_field_index(
            tela_impressao, 'TComboBox', 'nome_impressora'
        )
        combo_nome_impressora.wait('ready', timeout=5)
        combo_nome_impressora.select('EPSON3B3537 (L4260 Series)')

        #tela_impressao.OK.click()
        cancelar_button = get_field_title(
            tela_impressao, 'TButton', 'Cancelar'
        )
        cancelar_button.click()

    except Exception as e:
        raise RuntimeError(f'Erro no menu da impressão: {e}')

