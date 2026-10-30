# Recursos explícitos; sem diário, configurações privadas ou dados de negócio.
from pathlib import Path

raiz = Path(SPECPATH)
a = Analysis([str(raiz / 'impressao.py')], pathex=[str(raiz)],
    datas=[(str(raiz / 'src' / nome), 'src') for nome in
           ('impressao.html', 'impressao.css', 'impressao.js', 'rolagem.js', 'nunes-tema.js')]
          + [(str(raiz / 'icons' / nome), 'icons') for nome in
             ('icone.ico', 'icone.svg', 'icone-192.png', 'tema-lua.svg', 'tema-lua-sol.svg')]
          + [(str(raiz / 'desktop-winforms.config'), '.')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms',
                   'win32com.propsys.propsys', 'win32com.propsys.pscon', 'win32com.shell.shell'],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Impressao OPs',
          console=False, icon=str(raiz / 'icons/icone.ico'), uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, name='Impressao OPs')
