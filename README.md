# Impressão de OPs · Nunes

Painel web local para imprimir ordens de produção no Sisplan por **De / Para** ou por **Lista de OPs**. A lista é digitada ou colada na interface; não há carregamento de arquivo. O fluxo de console em `main.py` continua disponível.

A abertura padrão agora usa a janela desktop, com preparação/conferência e
acompanhamento no padrão Cofre/Busca e Move. Consulte [DESKTOP.md](DESKTOP.md)
para preparar o ambiente separado de 32 bits, abrir, empacotar e validar.
As instruções de navegador abaixo continuam válidas usando `impressao.py --web`.

## Instalação e abertura

Use Python de **32 bits**, compatível com a automação Sisplan já utilizada nos projetos Nunes. Na pasta do projeto:

```powershell
& "$env:LOCALAPPDATA\Python\Python313-32\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No painel, clique em **Selecionar impressora**, escolha uma das filas instaladas no Windows e clique em **Usar impressora**. A lista inclui impressoras locais, conexões de rede instaladas para o usuário e filas virtuais. **Atualizar lista** consulta novamente o Windows. A presença na lista não garante que o equipamento esteja ligado; filas virtuais podem solicitar um local para salvar o arquivo.

A última impressora utilizada é salva após o primeiro envio concluído pela automação, em `%LOCALAPPDATA%\Nunes\ImpressaoOPs\config.json`, e restaurada na próxima abertura, independentemente do navegador. Apenas escolher uma fila não substitui a última utilizada. **Console e web usam a mesma prioridade:** a última impressora salva prevalece sobre `IMPRESSORA_OP`; a variável é usada somente sem preferência salva. Na web, uma escolha explícita válida para o lote prevalece sobre a seleção inicial.

Se a fila salva tiver sido removida ou renomeada, a ferramenta informa o problema e não escolhe outra silenciosamente pela variável de ambiente. Selecione uma fila válida no painel; a nova preferência será salva após o primeiro envio concluído. Uma preferência ilegível mantém um aviso, mesmo quando a variável fornece uma fila válida.

A seleção permanece fixa durante todo o lote, inclusive entre setores, no console e na web. O console valida a fila e exibe **Impressora do lote** antes de iniciar a automação do Sisplan; também registra o nome no diário operacional. Alterações de ambiente ou preferência durante a execução não trocam a fila desse lote. Na web, a impressora é validada novamente antes de iniciar. Se outra aba tiver alterado a seleção, confira a impressora exibida e prepare o lote novamente. Uma falha ao salvar a preferência é exibida no console ou painel e registrada no log, sem interromper nem repetir os envios.

Abra `Abrir Impressao OPs.cmd` para a janela desktop. Para usar o navegador,
execute `.\.venv\Scripts\python.exe impressao.py --web`: o painel abre em
`http://127.0.0.1:8766`, acessível somente neste computador, e o tema fica salvo
no navegador. No desktop, a porta é dinâmica e tema/posição são persistidos
localmente. Uma nova abertura desktop ativa a janela existente; uma instância
web anterior deve ser encerrada normalmente antes de mudar de modo.

Para criar um atalho com o ícone Nunes, execute `Criar Atalho Impressao OPs.ps1`; o arquivo `.lnk` é criado na própria pasta e pode ser copiado para a área de trabalho. Recrie-o se mover o projeto.

## Diagnóstico de abertura

A abertura registra as etapas em `logs/impressao-ops-abertura.log`, na pasta
de presença da sessão Nunes. Diário local, preferência/enumeração de impressoras
e criação do servidor têm tempos separados. Essa medição não envia impressão.
Reabra a aplicação para carregar a mudança. Resultados e limites estão em
[Tempos por etapa](../nunes-hub/TEMPOS_ABERTURA.md).

## Como usar

1. Abra o Sisplan da empresa **002** no relatório de facção (`RelFaccao01`), aba **Envio**.
   Confira a impressora exibida no painel e use **Selecionar impressora** para escolher ou trocar a fila.
2. Em **De / Para**, informe intervalos inclusivos e seus setores. “Para” vazio significa uma única OP. Use **Adicionar intervalo** para outros lotes.
3. Em **Lista de OPs**, cole os números e informe o setor comum. Aceita linhas, espaços, vírgulas e ponto e vírgula. O setor vazio assume **10**, como no console.
4. Clique em **Conferir OPs**, revise a conferência e clique em **Imprimir lote**. Alterações na entrada exigem nova conferência. Uma nova execução precisa de uma nova conferência, inclusive após falha.
5. Acompanhe o envio por OP. **Parar após a OP atual** termina a ação em andamento antes de interromper. **Encerrar** pede confirmação, aguarda essa ação e fecha o serviço local. Ao fechar a aba, o navegador também pede confirmação; cancelar mantém o painel e o processamento. Confirmar a saída da última aba encerra o programa após uma tolerância de três segundos, respeitando a OP em andamento. Essa tolerância permite recarregar a página sem encerrar o programa. Se houver outra aba do painel aberta, o programa continua disponível nela.

A confirmação de saída usa o aviso padrão do navegador, também exibido ao recarregar ou navegar para outra página. O navegador controla o texto e só permite esse aviso depois de uma interação do usuário com a página. Fechamentos forçados do navegador não garantem exibição da confirmação; a desconexão do canal ainda permite ao servidor detectar a saída.

O acompanhamento usa uma conexão contínua que envia o estado apenas quando há mudanças. Quando o painel está parado, não há consultas periódicas de estado nem redesenho da tela. Mensagens internas mantêm a conexão aberta para detectar o fechamento da aba, sem alterar a interface.

As OPs recebem no mínimo seis dígitos. Repetições da mesma OP no mesmo setor são eliminadas na execução; uma mesma OP em setores diferentes permanece. Limite: 5.000 OPs por execução e 100 intervalos. A conferência exibe até 100 números de cada lote e informa quantos não estão visíveis; o lote completo é processado. A atividade mantém os últimos 50 envios da execução em memória. O diário persistente da E9 guarda o lote completo e as incertezas, sem retomada automática. O histórico acumulado de métricas fica separado, conforme a seção Estatísticas no Hub Nunes.

Durante a execução, deixe teclado e mouse livres para a automação. O painel utiliza a sequência de campos e atalhos existente em `main.py` e `src/handle_app.py`. Na interface web e no console, cada OP tem **uma tentativa**: uma falha pode acontecer após o envio e interrompe o lote sem repetição automática. Confira a última OP e o papel antes de preparar outra execução. O contador indica envios concluídos pelo fluxo de automação; não confirma a saída física. Erros técnicos ficam em `impressao.log`.

O modo de console mantém `MODO_ENTRADA` em `main.py` e a leitura de `ordem_producao.txt` no modo `arquivo`. Desde a E2 (20/10/2026), qualquer falha interrompe também as OPs e os setores seguintes, identifica a OP afetada e orienta conferir a fila da impressora e o papel antes de iniciar outra execução. O console retorna código 1 em caso de falha e 0 ao concluir ou quando não há OPs, permitindo ao contrato do Hub registrar o erro. Não há repetição automática nem parâmetro para habilitá-la no executor compartilhado.

## Visual e implementação

Visual adaptado ao [guia de telas Nunes](../estrutura-nunes/identidade-visual/interfaces/guia-telas-automacoes.md),
com Cofre e Busca e Move como referências: preparação/conferência à esquerda,
impressora e andamento à direita, histórico recolhido abaixo, tema no cabeçalho e Encerrar com ícone no
rodapé. Temas claro/escuro, com escuro por padrão e preferência persistida.
O ícone coração com N conserva a cor `#475569`. A assinatura **g2mello · Essencial**
inclui os dois traços sob os `l` e o link de autoria. Os recursos ficam neste
projeto; sua execução não depende do caminho do hub.

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

**Total** conta cada novo envio concluído, incluindo novas solicitações da mesma OP.
**Reimpressões** conta cada ocorrência após a primeira do mesmo número de OP em
todo o histórico disponível, independentemente do setor; já está incluída no total.
Os contadores respeitam as datas aplicadas no Hub e também aparecem por dia.
Não há contador de OPs distintas na interface. O indicador não comprova a saída
física do papel. Repetições descartadas pelo contador antigo não podem ser
reconstruídas; seus registros existentes são preservados.

O diário migra automaticamente de v1 para v2, conservando os envios e incertezas.
A partir desta atualização, cada conclusão cria uma pendência de estatística na
mesma transação. A publicação usa o ID do envio, o lote e o instante persistido;
reabrir ou republicar não duplica nem reimprime. Pendências são tentadas novamente
na abertura e após outra conclusão. Se só o diário tiver aceitado a estatística,
o Hub ainda não a conhece; consulte o log e reabra a ferramenta após resolver a
indisponibilidade. Conclusões antigas não são importadas novamente para evitar
duplicação com o contador anterior. Preserve o diário e as métricas no backup.

O registro funciona na interface web e no console, mesmo com o hub fechado. O módulo `metricas_nunes.py` é distribuído a partir do Hub Nunes; seu README documenta armazenamento, recuperação, filtros e exportação. Feche e reabra esta ferramenta após atualizar. O histórico começa com esta versão e não importa operações anteriores. Falhas na estatística não repetem nem interrompem operações concluídas; uma fila local recupera gravações transitórias e falhas de persistência são registradas no log. Antes de rodar a suíte completa, use um terminal exclusivo de testes e configure NUNES_METRICAS_DADOS para uma pasta temporária; o README do Hub Nunes contém o comando de isolamento.


## Sincronização com a central local

As entradas `impressao.py` e `main.py` enviam os eventos locais `op_enviada`
já persistidos, incluindo o histórico anterior ao vínculo. A identidade
de cada envio e o instante são preservados: reenvios da mesma métrica não aumentam
a contagem; uma nova impressão concluída gera outra métrica. A sincronização não imprime,
não acessa o Sisplan nem resolve incertezas do diário operacional. Conferir
manualmente um envio continua sem criar métrica ou comprovante físico.

Na pasta `nunes-estatisticas`, com a central já preparada, execute uma vez:

```powershell
.\.venv\Scripts\python.exe central.py vincular --automacao '..\auto-impressao-ops'
```

O comando cria `.local/central.json` privado e recusa sobrescrever vínculo
existente. Reinicie a central atualizada e reabra Impressão de OPs e Hub.
Não recrie bancos, identidade ou configuração da central. Sem vínculo, a
ferramenta mantém o comportamento local e não faz envios à central.

O sincronizador tenta enviar na abertura e ao encerrar. A espera entre ciclos
é de cinco segundos, subindo gradualmente até 30 segundos somente sem atividade
nem pendências; atividade ou falha retomam cinco segundos.
O fechamento espera até 2,5 segundos. Central desligada, resposta perdida ou
confirmação inválida conservam pendências para outra abertura. Os registros
originais e a fila `recuperar` não são removidos. As confirmações ficam em
`sincronizacao-impressao-ops.sqlite3` na pasta das métricas, vinculadas à
identidade da central e à assinatura do evento.

Para consultar ou enviar estatísticas sem imprimir, na pasta desta ferramenta:

```powershell
.\.venv\Scripts\python.exe sincronizar_estatisticas.py --aplicacao impressao-ops --resumo
.\.venv\Scripts\python.exe sincronizar_estatisticas.py --aplicacao impressao-ops
```

No Hub, **Resultados → Impressão de OPs** mostra os contadores locais; **Conferir
agora** atualiza essa consulta uma única vez. A API da central conserva o total
recebido e as pendências. Os filtros e agrupamentos do histórico local são
independentes; números centrais e locais não são somados. O cliente funciona
sem importar repositórios irmãos. Executáveis antigos precisam ser reconstruídos
com `contrato_estatisticas.py`, `sincronizar_estatisticas.py` e `metricas_nunes.py`.
Protocolo, backup e limites no [contrato da central](../nunes-estatisticas/CONTRATO.md).

Validação de 22/10/2026: 68 testes Python e oito JavaScript da Impressão
aprovados, incluindo nove testes novos da central. O conjunto dos sete projetos
envolvidos somou 923 Python e 81 JavaScript, com tipagem completa do Financeiro
sem erros ou avisos. Os cenários usam métricas, diários e central temporários;
Sisplan e impressoras são simulados. Não houve impressão real. O vínculo privado
foi criado após os testes; homologação operacional pendente após reiniciar
a central e reabrir as interfaces.

## Recuperação de impressão — E9, 21/10/2026

Painel e console salvam o lote antes de trabalhar e registram o início antes
de cada tentativa. O diário fica em `%LOCALAPPDATA%\Nunes\ImpressaoOPs\execucoes.sqlite3`;
`NUNES_OPS_DADOS` permite escolher outra pasta, inclusive temporária para testes.
Ele começa nesta versão e não importa métricas como comprovantes de impressão.

**Histórico e recuperação** exibe o último lote inteiro e todas as incertezas
anteriores, com OP, setor, impressora e horário. “Não iniciada” permanece
distinta de “Envio concluído pelo fluxo” e “Incerto”. Um início sem conclusão,
inclusive por término abrupto, bloqueia novos lotes antes de enviar outra OP.
Falha ao salvar o início impede o envio; falha ao salvar a conclusão conserva
a incerteza. Arquivo inválido ou indisponível bloqueia a operação, sem apagá-lo.

Confira a fila **e o papel**. Use **Conferi: foi enviado** ou **Conferi: não foi
enviado**, confirmando a decisão. A ação só registra a conferência manual;
não imprime nem lança uma métrica. Após resolver as incertezas, prepare e
confira um novo lote apenas com as OPs desejadas. Pendentes e concluídas não
são reenviadas automaticamente. Uma nova impressão pelo botão é uma nova
solicitação explícita e acrescenta outra ocorrência nas métricas após conclusão.

O responsável também pode consultar ou registrar a conferência pelo console:

```powershell
.\.venv\Scripts\python.exe recuperar_impressao.py
.\.venv\Scripts\python.exe recuperar_impressao.py --id IDENTIFICADOR --resultado conferido_nao_enviado --conferi-fila-e-papel
```

O identificador vem da consulta. O outro resultado permitido é
`conferido_enviado`. O contrato do Hub conserva a exclusão Sisplan também
nesse comando. A conferência não é permitida com impressão em andamento.
“Concluído pelo fluxo” continua sem provar saída física; uma marca manual
também não produz recibo do spooler. Uma falha depois do envio e antes da
conclusão pode exigir conferência mesmo quando o papel já saiu. O intervalo
entre efeito e métrica permanece documentado no Hub como R06.

Validação: 50 testes Python e oito JavaScript aprovados, incluindo falhas antes
e depois do envio, API protegida, parada e persistência do lote além de 50 OPs.
Um processo de teste terminou abruptamente e outro recuperou concluído,
incerto e pendente. Prévia Edge verificada em claro/escuro a 360/1200 px.
Somente dados sintéticos; nenhuma OP foi impressa. Reabra a ferramenta para
carregar a atualização; executáveis anteriores precisam ser reconstruídos.

## Padronização da impressora — 21/10/2026

O console passou a usar o gerenciador de impressoras existente na web, com
validação antes de iniciar o Sisplan e seleção fixa para todas as OPs/setores
da execução. Não há novo arquivo de configuração, dependência ou alteração
do formato do diário. A regra de preferência está em **Instalação e abertura**.

Passaram **59 testes Python e oito JavaScript**, incluindo nove regressões
Python novas. O teste entre console e web usa a mesma preferência salva com
ambiente divergente. Também foram conferidos ausência/remoção de fila, falha
de consulta, escolha fixa entre setores, preferência ilegível, persistência
após sucesso e falha de gravação sem repetir o envio. A proteção contra seleção
de outra aba e os testes de recuperação/métricas continuam passando.

Somente impressoras e controles simulados, HTTP local de teste e diretórios
isolados; nenhuma OP real foi impressa nem houve interação com o Sisplan.
Feche e reabra a ferramenta para carregar a mudança; executáveis antigos
precisam ser reconstruídos. Homologação física de impressão permanece separada.
