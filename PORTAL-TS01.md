# Impressão de OPs pelo navegador no TS01

O IIS autentica a conta Windows da operadora. O executor roda na sessão
interativa do TS01 com Sisplan aberto e acesso à fila de impressão. As
consultas vão para a API do Sisplan com a identidade
Windows do executor. A operadora pode acompanhar e pedir parada após a OP
atual. Fechar o navegador deixa o lote em andamento e o executor disponível.

## Instalação por um comando

Extraia os dois ZIPs em `C:\Nunes` e copie [o instalador PowerShell](Instalar%20Impressao%20OPs%20TS01.ps1)
para essa pasta. No TS01, abra o Windows PowerShell como administrador com
permissão para criar ou atualizar os dois grupos no domínio. Use as contas reais
da operadora e do executor.

```powershell
& 'C:\Nunes\Instalar Impressao OPs TS01.ps1' -ContaOperadora 'GRATITUDE\usuario-operadora' -ContaExecutor 'GRATITUDE\ADM07' -ArquivoBanco 'C:\Nunes\privado\banco-sisplan.json'
```

O instalador aproveita um certificado válido para `ts01.gratitude.local` no
repositório **Computador Local → Pessoal**. Se houver mais de um, informe
`-Certificado` com a impressão digital. O JSON deve ter uma credencial de
leitura dedicada. Se ele já estiver na pasta privada da API, dispense
`-ArquivoBanco`.

O instalador habilita os componentes necessários, configura e inicia os dois
sites, adiciona as contas aos grupos, cria o `portal.json` e registra a tarefa
`Nunes Impressao de OPs` para o logon. Se precisar liberar as portas no firewall
local, informe a rede autorizada com `-RedePermitida`, por exemplo
`-RedePermitida LocalSubnet` se as estações estiverem na sub-rede do TS01.
Após mudanças de grupo, renove a sessão Windows das contas antes de testar.

## Instalar

1. Extraia os ZIPs do portal e da API em `C:\Nunes`. Os diretórios de instalação
   são `ImpressaoOpsPortal` e `NunesApiSisplan`. Se já houver uma instalação da API, preserve a
   configuração privada e atualize o programa pela rotina de manutenção do IIS.
   Confira a disponibilidade das portas HTTPS antes de configurar os vínculos.
   Os exemplos usam `8771` para o portal e `8772` para a API. A porta `443`
   atende ao RD Web Access, a `8769` à Central e a `8770` ao Financeiro.
2. No domínio, autorize a operadora no grupo de segurança
   `GRATITUDE\ImpressaoOPs-Operacao`, usado pelo IIS para o portal. Autorize a
   conta Windows do executor no grupo `GRATITUDE\ImpressaoOPs-Consulta`, usado
   pela API. Após alterar a associação, inicie uma nova sessão Windows da conta.
3. Provisione a credencial de leitura e o site da API conforme
   o `README.md` do pacote da API. Use certificado confiável para
   `ts01.gratitude.local`. Valide o acesso HTTPS à API usando a conta do executor
   **a partir do TS01**. Em caso de erro de autenticação, confira a identidade
   do IIS, as configurações de autenticação do Windows e os registros do IIS.
4. Crie `C:\Nunes\ImpressaoOpsPortal\privado` e restrinja sua ACL à administração,
   ao pool do site do portal e à conta do executor. O pool e o executor precisam
   apenas de leitura nessa pasta. Gere uma vez o segredo do encaminhamento local
   em PowerShell administrativo, após preparar a ACL.

```powershell
$configPortalOps = 'C:\Nunes\ImpressaoOpsPortal\privado\portal.json'
$bytesPortalOps = New-Object byte[] 32
$rngPortalOps = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rngPortalOps.GetBytes($bytesPortalOps) } finally { $rngPortalOps.Dispose() }
$jsonPortalOps = @{
    origem = 'https://ts01.gratitude.local:8771'
    porta_executor = 18771
    porta_api = 8772
    segredo = [BitConverter]::ToString($bytesPortalOps).Replace('-', '').ToLowerInvariant()
} | ConvertTo-Json
$jsonPortalOps | Out-File -LiteralPath $configPortalOps -Encoding ascii -NoClobber
```

Use portas livres e ajuste o exemplo aos vínculos reais. A porta do executor
é de loopback e permanece fechada para a rede. Para trocar o segredo, atualize
o JSON privado em uma janela de manutenção e reinicie o executor.

## Configurar o IIS

Crie o site dedicado `ImpressaoOpsPortal`, em pool próprio **Integrated**,
sem código gerenciado, apontado para `C:\Nunes\ImpressaoOpsPortal\site`.
O pool precisa de leitura em `site` e leitura e execução em `gateway`.
Use os recursos **CGI**, **Windows Authentication** e **URL Authorization**
do IIS. O `site\web.config` distribui a regra do grupo e o encaminhamento
para `gateway\PortalOps.exe`. Se mudar a pasta base, ajuste `scriptProcessor`.

Com o site parado, configure só o binding HTTPS dedicado, com certificado
confiável e nome `ts01.gratitude.local`. Habilite apenas a Autenticação do
Windows em **Authentication**. Execute em PowerShell administrativo.

```powershell
$appCmdPortalOps = Join-Path $env:windir 'System32\inetsrv\appcmd.exe'
& $appCmdPortalOps set config ImpressaoOpsPortal /section:system.webServer/security/authentication/anonymousAuthentication /enabled:false /commit:apphost
& $appCmdPortalOps set config ImpressaoOpsPortal /section:system.webServer/security/authentication/windowsAuthentication /enabled:true /commit:apphost
& $appCmdPortalOps set config ImpressaoOpsPortal /section:system.webServer/security/access /sslFlags:Ssl /commit:apphost
& $appCmdPortalOps set config ImpressaoOpsPortal /section:system.webServer/cgi /createProcessAsUser:false /timeout:00:00:35 /commit:apphost
```

Confira as regras efetivas de autorização e os requisitos de delegação de
seções descritos no guia da API. Permita apenas o executável exato do gateway
se o IIS exigir uma entrada em **ISAPI and CGI Restrictions**. Libere a porta
HTTPS do portal somente para a rede interna prevista.

## Executar e homologar

Na sessão com o Sisplan aberto, execute:

```powershell
& 'C:\Nunes\ImpressaoOpsPortal\executor\Impressao OPs.exe' --portal 'C:\Nunes\ImpressaoOpsPortal\privado\portal.json'
```

O executor precisa conseguir gravar `impressao.log` em `executor`, além dos
dados do aplicativo no perfil Windows. Em instalação restrita, crie o arquivo
de log e conceda gravação apenas nele. Para abrir pelo Agendador no logon,
use esse executável e argumentos, selecione **Executar somente quando o
usuário estiver conectado**, desative o limite de duração e evite instâncias
simultâneas. Use Ctrl+C no console ou a parada cooperativa pelo Hub para
encerrar o executor.

Com as versões atualizadas do Financeiro e da Impressão, os dois executores
podem ficar abertos na mesma sessão. Cada um reserva o Sisplan ao iniciar
uma operação gráfica. Se estiver ocupado, aguarde a operação atual e tente
novamente no portal. Atualize os dois executáveis antes de operar juntos.
Homologue as duas telas do Sisplan, a impressora e as condições de RDP ou
bloqueio que serão usadas na prática.

No PC da operadora, abra `https://ts01.gratitude.local:8771/` com a conta
autorizada. Teste conferência, saída de uma OP na fila já configurada, recusa
de uma conta fora do grupo e reabertura do painel durante um lote sintético
ou controlado. O portal reserva o painel para uma conta por vez, liberando
outra após dois minutos sem atividade e com a impressão ociosa.

No Edge, instale pelo menu **Mais ferramentas → Aplicativos → Instalar este
site como um aplicativo** e fixe na barra de tarefas.

## Recriar o ZIP

Execute `Build Portal TS01.ps1` na estação de build com o ambiente desktop
de 32 bits. O script gera um pacote novo em `.local\entregas` e imprime o
SHA-256. A configuração privada é provisionada diretamente no servidor.
