# Impressão de OPs desktop

A entrada `impressao.py` abre uma janela pywebview/WinForms com WebView2,
usando o servidor HTTP local autenticado existente. O fluxo de console em
`main.py` continua separado. Não executa impressão ao abrir.

## Ambiente e abertura

Use Python 3.13 **32 bits**, preservando a arquitetura da automação Sisplan.
O ambiente desktop é separado do `.venv` anterior:

```powershell
py -3.13-32 -m venv .venv-desktop
& .\.venv-desktop\Scripts\python.exe -m pip install -r requirements-build.txt
& '.\Abrir Impressao OPs.cmd'
& '.\Criar Atalho Impressao OPs.ps1'
```

Windows precisa de .NET Framework 4.8 e WebView2 Evergreen disponíveis.
`requirements-desktop.txt` contém as dependências para executar pelo fonte;
`requirements-build.txt` acrescenta o empacotador. O painel no navegador continua
disponível por `impressao.py --web`, usando o ambiente anterior se desejado.

O Hub passa a preferir `.venv-desktop` e ativa a mesma janela ao abrir novamente.
A instância e a exclusividade do Sisplan pertencem à mesma sessão Windows.
Uma instância web anterior precisa ser encerrada normalmente antes de abrir o desktop.

## Interface e contratos preservados

Layout baseado em Cofre/Busca e Move: preparação e conferência à esquerda,
impressora e andamento à direita, histórico recolhido abaixo, tema no cabeçalho
e Encerrar no rodapé. Pendências de envio têm alerta e atalho para revisão.
Em larguras estreitas, os painéis ficam empilhados. A rolagem usa indicador
sobreposto, sem reservar faixa. A lista de impressoras permanece em diálogo.

Conferir OPs continua obrigatório antes de Imprimir lote. Alterações invalidam
a conferência; a impressora permanece fixa no lote e sua preferência é salva
apenas após o primeiro envio concluído. Falha não provoca repetição automática.
O histórico de incertezas e a conferência da fila/papel permanecem disponíveis.

X e Encerrar pedem confirmação. A OP em andamento e a gravação do diário terminam
antes de a janela desaparecer; a sincronização auxiliar termina depois, no processo,
mantendo a exclusividade até a saída. Parada pelo Hub respeita a mesma fronteira.
Não confundir janela fechada com processo terminado. Uma falha ao salvar o tema
pela interface impede a saída por X/Encerrar até uma gravação bem-sucedida.

Tema e geometria ficam separados da seleção de impressora, em
`%LOCALAPPDATA%\Nunes\ImpressaoOPs\desktop-tema.json` e `desktop-janela.json`.
O tema desktop é persistido no backend, independentemente da porta ou cookies.
Diário e métricas conservam os destinos descritos no README.

`dpi_windows.py`, `desktop_windows.py` e `desktop-winforms.config` são cópias locais
da fonte no Hub, declaradas no manifesto. A aplicação não importa repositórios irmãos.
Segue o [padrão de DPI](../estrutura-nunes/identidade-visual/interfaces/desktop-dpi.md).

## Pacote

```powershell
& '.\Build Desktop.ps1'
```

Distribua a pasta inteira `dist\Impressao OPs`, incluindo `_internal`.
O pacote não contém configurações privadas, diário, `.env`, dados operacionais
ou ambiente virtual. Não instala runtimes nem substitui uma instalação existente.
Atalhos e identidade Windows usam o ícone local da Impressão.

## Verificação

Use diretórios isolados para métricas e executores falsos. Testes automatizados
não imprimem nem controlam Sisplan:

```powershell
& .\.venv-desktop\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_impressao_ui.cjs
& .\.venv-desktop\Scripts\python.exe -m tests.ensaio_desktop
& .\.venv-desktop\Scripts\python.exe -m tests.verificar_pacote_desktop --exe 'dist\Impressao OPs\Impressao OPs.exe'
```

O ensaio desktop usa diário, filas e preferências sintéticos. Confere o WebView2
real, temas, larguras e excedente de conteúdo. A homologação da impressão real,
monitores físicos em 100%/125% e pacotes em outras máquinas é separada e requer
ambiente apropriado; ensaio sintético não comprova saída de papel ou conexão Sisplan.

Verificação local em 30/10/2026: dependências compatíveis no Python 3.13.13 de
32 bits, com importação conjunta de WebView2 e adaptador Sisplan. Passaram os
75 testes Python existentes, seis novos testes de ciclo desktop/finalização e
14 testes JavaScript. O ensaio WebView2 passou em 17 cenários (temas, larguras,
excedente de conteúdo, maximização e zoom de 200%), além de conferência sem
execução, invalidação após edição, tema persistido e diálogo de impressoras.
A transição manual de tema segue a Cofre, com movimento reduzido respeitado
e conteúdo recolhido sem transição tardia; ambos foram verificados no WebView2.
O pacote de 32 bits confirmou abertura, presença, reativação da mesma instância
e parada pelo Hub com dados isolados. As cópias dos três recursos desktop
compartilhados coincidem com a fonte por SHA-256.

Evidências locais de fonte ficam em `.local/qa-desktop`. Não houve impressão
real nem homologação entre dois monitores físicos em 100%/125%.
