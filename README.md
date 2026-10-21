# Impressão de OPs · Nunes

Painel web local para imprimir ordens de produção no Sisplan por **De / Para** ou por **Lista de OPs**. A lista é digitada ou colada na interface; não há carregamento de arquivo. O fluxo de console em `main.py` continua disponível.

## Instalação e abertura

Use Python de **32 bits**, compatível com a automação Sisplan já utilizada nos projetos Nunes. Na pasta do projeto:

```powershell
& "$env:LOCALAPPDATA\Python\Python313-32\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No painel, clique em **Selecionar impressora**, escolha uma das filas instaladas no Windows e clique em **Usar impressora**. A lista inclui impressoras locais, conexões de rede instaladas para o usuário e filas virtuais. **Atualizar lista** consulta novamente o Windows. A presença na lista não garante que o equipamento esteja ligado; filas virtuais podem solicitar um local para salvar o arquivo.

A última impressora utilizada é salva após o primeiro envio concluído pela automação, em `%LOCALAPPDATA%\Nunes\ImpressaoOPs\config.json`, e restaurada na próxima abertura, independentemente do navegador. Apenas escolher uma fila não substitui a última utilizada. Se a fila tiver sido removida ou renomeada, selecione outra antes de imprimir. Sem preferência salva, o painel aproveita `IMPRESSORA_OP`, se corresponder a uma fila instalada. O console continua usando essa variável de ambiente.

A seleção permanece fixa durante todo o lote, inclusive entre setores; não é possível trocá-la durante a execução. A impressora é validada novamente antes de iniciar. Se outra aba tiver alterado a seleção, confira a impressora exibida e prepare o lote novamente. Uma falha ao salvar a preferência é exibida no painel e registrada no log, sem interromper os envios.

Abra `Abrir Impressao OPs.cmd` ou execute `.\.venv\Scripts\python.exe impressao.py`. O painel abre em `http://127.0.0.1:8766`, acessível somente neste computador. A porta fixa também preserva a preferência de tema no mesmo navegador. Se outra instância estiver aberta ou a porta estiver ocupada, a abertura informa a falha.

Para criar um atalho com o ícone Nunes, execute `Criar Atalho Impressao OPs.ps1`; o arquivo `.lnk` é criado na própria pasta e pode ser copiado para a área de trabalho. Recrie-o se mover o projeto.

## Como usar

1. Abra o Sisplan da empresa **002** no relatório de facção (`RelFaccao01`), aba **Envio**.
   Confira a impressora exibida no painel e use **Selecionar impressora** para escolher ou trocar a fila.
2. Em **De / Para**, informe intervalos inclusivos e seus setores. “Para” vazio significa uma única OP. Use **Adicionar intervalo** para outros lotes.
3. Em **Lista de OPs**, cole os números e informe o setor comum. Aceita linhas, espaços, vírgulas e ponto e vírgula. O setor vazio assume **10**, como no console.
4. Clique em **Conferir OPs**, revise a conferência e clique em **Imprimir lote**. Alterações na entrada exigem nova conferência. Uma nova execução precisa de uma nova conferência, inclusive após falha.
5. Acompanhe o envio por OP. **Parar após a OP atual** termina a ação em andamento antes de interromper. **Encerrar** pede confirmação, aguarda essa ação e fecha o serviço local. Ao fechar a aba, o navegador também pede confirmação; cancelar mantém o painel e o processamento. Confirmar a saída da última aba encerra o programa após uma tolerância de três segundos, respeitando a OP em andamento. Essa tolerância permite recarregar a página sem encerrar o programa. Se houver outra aba do painel aberta, o programa continua disponível nela.

A confirmação de saída usa o aviso padrão do navegador, também exibido ao recarregar ou navegar para outra página. O navegador controla o texto e só permite esse aviso depois de uma interação do usuário com a página. Fechamentos forçados do navegador não garantem exibição da confirmação; a desconexão do canal ainda permite ao servidor detectar a saída.

O acompanhamento usa uma conexão contínua que envia o estado apenas quando há mudanças. Quando o painel está parado, não há consultas periódicas de estado nem redesenho da tela. Mensagens internas mantêm a conexão aberta para detectar o fechamento da aba, sem alterar a interface.

As OPs recebem no mínimo seis dígitos. Repetições da mesma OP no mesmo setor são eliminadas na execução; uma mesma OP em setores diferentes permanece. Limite: 5.000 OPs por execução e 100 intervalos. A conferência exibe até 100 números de cada lote e informa quantos não estão visíveis; o lote completo é processado. A atividade mantém os últimos 50 envios da execução em memória, sem retomada automática. O histórico acumulado de métricas fica separado, conforme a seção Estatísticas no Hub Nunes.

Durante a execução, deixe teclado e mouse livres para a automação. O painel utiliza a sequência de campos e atalhos existente em `main.py` e `src/handle_app.py`. Na interface web e no console, cada OP tem **uma tentativa**: uma falha pode acontecer após o envio e interrompe o lote sem repetição automática. Confira a última OP e o papel antes de preparar outra execução. O contador indica envios concluídos pelo fluxo de automação; não confirma a saída física. Erros técnicos ficam em `impressao.log`.

O modo de console mantém `MODO_ENTRADA` em `main.py` e a leitura de `ordem_producao.txt` no modo `arquivo`. Desde a E2 (20/10/2026), qualquer falha interrompe também as OPs e os setores seguintes, identifica a OP afetada e orienta conferir a fila da impressora e o papel antes de iniciar outra execução. O console retorna código 1 em caso de falha e 0 ao concluir ou quando não há OPs, permitindo ao contrato do Hub registrar o erro. Não há repetição automática nem parâmetro para habilitá-la no executor compartilhado.

## Visual e implementação

Visual baseado nos painéis locais de `nunes-contas-receber` e `auto-pedidos-havan`: cartões, conferência, andamento e temas claro/escuro, com preferência inicial do sistema e alternância manual. O ícone coração com N, cor `#475569`, foi copiado das exportações de `auto-impressao-ops` do hub `estrutura-nunes`. A assinatura **g2mello · Essencial** inclui os dois traços sob os `l` e o link de autoria. Os recursos ficam neste projeto; sua execução não depende do caminho do hub.

O servidor usa a biblioteca padrão Python, sem framework web ou build de frontend. Apenas a execução real importa `pywinauto`. Os comandos da API exigem token da sessão, origem local e Host correspondente; a conferência não acessa o Sisplan nem a impressora.

## Verificação

O contrato `integracao_hub.py`, mantido no Hub Nunes, publica saúde e estado e
permite pedir a parada segura pelo monitor. A trava compartilhada por usuário
e sessão impede executar outra ferramenta Sisplan enquanto Impressão estiver
ativa, inclusive pelo console. Ela permanece até o executor terminar. Fechar
a última aba encerra o servidor após a tolerância de reconexão e a parada
segura; se nenhuma aba conectar inicialmente, o limite é de dois minutos.
Os atalhos Python incorporam essas mudanças; executáveis precisam ser refeitos.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check src/impressao.js
node --test tests/test_impressao_ui.cjs
```

Os testes usam entradas sintéticas, executor falso e HTTP local para conferir regras, concorrência, parada, falhas e proteção da API. Não imprimem nem controlam o Sisplan. A validação real de uma impressão continua separada dos testes.

Criado por Gabriel Mello · [g2mello](https://github.com/Gabriel2Mello)


## Estatísticas no Hub Nunes

O histórico conta o primeiro envio concluído de cada OP/setor; reenvios do mesmo par não aumentam o total. Uma OP em outro setor conta um novo envio. O indicador não comprova a saída física do papel. A atividade da execução continua em memória.

O registro funciona na interface web e no console, mesmo com o hub fechado. O módulo `metricas_nunes.py` é distribuído a partir do Hub Nunes; seu README documenta armazenamento, recuperação, filtros e exportação. Feche e reabra esta ferramenta após atualizar. O histórico começa com esta versão e não importa operações anteriores. Falhas na estatística não repetem nem interrompem operações concluídas; uma fila local recupera gravações transitórias e falhas de persistência são registradas no log. Antes de rodar a suíte completa, use um terminal exclusivo de testes e configure NUNES_METRICAS_DADOS para uma pasta temporária; o README do Hub Nunes contém o comando de isolamento.
