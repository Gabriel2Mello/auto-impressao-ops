#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)][string]$ContaOperadora,
    [string]$ContaExecutor = [Security.Principal.WindowsIdentity]::GetCurrent().Name,
    [string]$Certificado,
    [string]$ArquivoBanco,
    [ValidateRange(1024,65535)][int]$PortaPortal = 8771,
    [ValidateRange(1024,65535)][int]$PortaApi = 8772,
    [ValidateRange(1024,65535)][int]$PortaExecutor = 18771,
    [string[]]$RedePermitida
)
$ErrorActionPreference = 'Stop'
$nomeTs = 'ts01.gratitude.local'
$nomeTarefa = 'Nunes Impressao de OPs'
$programa = 'C:\Nunes\ImpressaoOpsPortal\executor\Impressao OPs.exe'
$configPortal = 'C:\Nunes\ImpressaoOpsPortal\privado\portal.json'
$configBanco = 'C:\Nunes\NunesApiSisplan\privado\banco-sisplan.json'
$argumentos = '--portal "' + $configPortal + '"'
$origemPortal = "https://${nomeTs}:$PortaPortal"
$sites = @(
    @{ Nome = 'NunesApiSisplan'; Porta = $PortaApi; Tempo = 22; Arquivo = $configBanco; Grupo = 'ImpressaoOPs-Consulta'
       Exe = 'C:\Nunes\NunesApiSisplan\programa\NunesApiSisplan.exe' },
    @{ Nome = 'ImpressaoOpsPortal'; Porta = $PortaPortal; Tempo = 35; Arquivo = $configPortal; Grupo = 'ImpressaoOPs-Operacao'
       Exe = 'C:\Nunes\ImpressaoOpsPortal\gateway\PortalOps.exe' }
)

if ($env:COMPUTERNAME -ine 'TS01') { throw 'Execute este instalador no TS01.' }
if (@(@($PortaPortal, $PortaApi, $PortaExecutor) | Select-Object -Unique).Count -ne 3) { throw 'Escolha tres portas distintas.' }
foreach ($item in $sites) {
    $item.Caminho = "C:\Nunes\$($item.Nome)\site"
    $item.Binding = "*:$($item.Porta):$nomeTs"
    $item.Pool = "IIS AppPool\$($item.Nome)"
    if (-not (Test-Path -LiteralPath $item.Exe -PathType Leaf)) { throw "Extraia o pacote atualizado de $($item.Nome) em C:\Nunes." }
    [xml]$web = Get-Content -LiteralPath (Join-Path $item.Caminho 'web.config') -Raw
    if ($web.configuration.'system.webServer'.handlers.add.scriptProcessor -ne $item.Exe) {
        throw "O web.config de $($item.Nome) aponta para outro executavel."
    }
    $autorizacao = $web.configuration.'system.webServer'.security.authorization
    $regras = @($autorizacao.SelectNodes('*'))
    if ($regras.Count -ne 2 -or $regras[0].LocalName -ne 'clear' -or
        $regras[1].LocalName -ne 'add' -or $regras[1].accessType -ne 'Allow' -or
        $regras[1].roles -ne "GRATITUDE\$($item.Grupo)" -or $regras[1].users) {
        throw "Confira as regras de autorizacao de $($item.Nome)."
    }
}
if (-not (Test-Path -LiteralPath $programa -PathType Leaf)) { throw 'Extraia o executor da Impressao de OPs.' }
$bancoJaExiste = Test-Path -LiteralPath $configBanco -PathType Leaf
$origemBanco = if ($bancoJaExiste) { $configBanco } else { $ArquivoBanco }
if (-not $origemBanco -or -not (Test-Path -LiteralPath $origemBanco -PathType Leaf)) {
    throw "Provisione a credencial de leitura em $configBanco ou indique o JSON privado com -ArquivoBanco."
}
if ($bancoJaExiste -and $ArquivoBanco -and
    (Get-FileHash -LiteralPath $ArquivoBanco).Hash -ne (Get-FileHash -LiteralPath $configBanco).Hash) {
    throw 'O JSON informado difere da configuracao existente. Preserve ou revise o arquivo no servidor.'
}
try {
    $perfil = (Get-Content -LiteralPath $origemBanco -Raw | ConvertFrom-Json).perfis.principal
    foreach ($campo in 'PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD') {
        if ($perfil.$campo -isnot [string] -or [string]::IsNullOrWhiteSpace($perfil.$campo)) { throw 'Campo ausente.' }
    }
} catch { throw 'Confira os cinco campos de texto do perfil principal no JSON privado da API.' }
if (Test-Path -LiteralPath $configPortal -PathType Leaf) {
    try { $atual = Get-Content -LiteralPath $configPortal -Raw | ConvertFrom-Json }
    catch { throw 'O portal.json existente esta invalido.' }
    if ($atual.origem -cne $origemPortal -or $atual.porta_executor -ne $PortaExecutor -or
        $atual.porta_api -ne $PortaApi -or $atual.segredo -cnotmatch '^[0-9a-f]{64}$') {
        throw 'O portal.json existente usa outros valores. Informe as portas ja configuradas.'
    }
}
$agora = Get-Date
$certs = @(Get-ChildItem Cert:\LocalMachine\My | Where-Object {
    $_.HasPrivateKey -and $_.NotBefore -le $agora -and $_.NotAfter -gt $agora -and
    ($_.DnsNameList.Unicode -contains $nomeTs -or $_.DnsNameList.Unicode -contains '*.gratitude.local') -and
    (-not $Certificado -or $_.Thumbprint -eq ($Certificado -replace '\s', ''))
})
if ($certs.Count -eq 0) {
    if ($Certificado) {
        throw "O certificado informado nao atende ao HTTPS de $nomeTs. Confira o thumbprint, o nome DNS, a validade e a chave privada em Cert:\LocalMachine\My."
    }
    throw "Nenhum certificado valido para $nomeTs com chave privada foi encontrado em Cert:\LocalMachine\My. Importe o PFX de servidor nesse repositorio."
}
if ($certs.Count -gt 1) {
    $thumbprints = ($certs.Thumbprint | Sort-Object) -join ', '
    throw "Mais de um certificado atende a $nomeTs. Execute novamente com -Certificado e um destes thumbprints: $thumbprints"
}
$cert = $certs[0]
foreach ($conta in $ContaOperadora, $ContaExecutor) {
    if ($conta -inotmatch '^GRATITUDE\\[^\\]+$') { throw 'Informe as contas como GRATITUDE\usuario.' }
    $null = [Security.Principal.NTAccount]::new($conta).Translate([Security.Principal.SecurityIdentifier])
}
$tarefa = Get-ScheduledTask -TaskName $nomeTarefa -TaskPath '\' -ErrorAction SilentlyContinue
if ($tarefa) {
    $sid = [Security.Principal.NTAccount]::new($ContaExecutor).Translate([Security.Principal.SecurityIdentifier]).Value
    if ($tarefa.Principal.UserId -notin @($ContaExecutor, $sid) -or $tarefa.Principal.LogonType -ne 'Interactive' -or
        @($tarefa.Actions).Count -ne 1 -or $tarefa.Actions[0].Execute -ne $programa -or $tarefa.Actions[0].Arguments -ne $argumentos -or
        $tarefa.Actions[0].WorkingDirectory -ne (Split-Path -Parent $programa) -or
        $tarefa.Settings.ExecutionTimeLimit -ne 'PT0S' -or $tarefa.Settings.MultipleInstances -ne 'IgnoreNew' -or
        @($tarefa.Triggers).Count -ne 1 -or $tarefa.Triggers[0].CimClass.CimClassName -ne 'MSFT_TaskLogonTrigger' -or
        $tarefa.Triggers[0].UserId -notin @($ContaExecutor, $sid)) {
        throw "A tarefa $nomeTarefa ja existe com outros parametros. Revise-a."
    }
}

Import-Module ServerManager
$faltam = @(Get-WindowsFeature -Name Web-Server,Web-CGI,Web-Windows-Auth,Web-Url-Auth,Web-Scripting-Tools,RSAT-AD-PowerShell |
    Where-Object { -not $_.Installed })
if ($faltam) {
    $instalacao = Install-WindowsFeature -Name $faltam.Name
    if (-not $instalacao.Success) { throw 'O Windows nao conseguiu instalar os recursos necessarios.' }
    if ($instalacao.RestartNeeded -eq 'Yes') { throw 'O Windows solicitou reinicio. Execute novamente apos o reinicio.' }
}
Add-Type -Path (Join-Path $env:windir 'System32\inetsrv\Microsoft.Web.Administration.dll')
$iis = [Microsoft.Web.Administration.ServerManager]::new()
try {
    foreach ($item in $sites) {
        $site = $iis.Sites[$item.Nome]
        if ($site -and ($site.Applications.Count -ne 1 -or $site.Applications['/'].VirtualDirectories.Count -ne 1 -or
            $site.Applications['/'].VirtualDirectories['/'].PhysicalPath -ne $item.Caminho -or
            $site.Applications['/'].ApplicationPoolName -ne $item.Nome -or $site.Bindings.Count -ne 1 -or
            $site.Bindings[0].Protocol -ne 'https' -or $site.Bindings[0].BindingInformation -ne $item.Binding)) {
            throw "O site $($item.Nome) ja existe com outra configuracao."
        }
        $pool = $iis.ApplicationPools[$item.Nome]
        if ($pool -and ($pool.ProcessModel.IdentityType -ne 'ApplicationPoolIdentity' -or
            $pool.ManagedRuntimeVersion -ne '' -or $pool.ManagedPipelineMode -ne 'Integrated')) {
            throw "O pool $($item.Nome) ja existe com outra configuracao."
        }
        foreach ($outro in $iis.Sites) {
            if ($outro.Name -eq $item.Nome) { continue }
            if (@($outro.Bindings | Where-Object { $_.BindingInformation -match ":$($item.Porta):[^:]*$" }).Count -or
                @($outro.Applications | Where-Object { $_.ApplicationPoolName -eq $item.Nome }).Count) {
                throw "A porta $($item.Porta) ou o pool de $($item.Nome) ja esta em uso pelo site $($outro.Name)."
            }
        }
        if (-not $site -and (Get-NetTCPConnection -LocalPort $item.Porta -State Listen -ErrorAction SilentlyContinue)) {
            throw "A porta $($item.Porta) ja esta em uso."
        }
    }

    Import-Module ActiveDirectory
    $dominio = Get-ADDomain -Identity 'gratitude.local'
    $dc = $dominio.PDCEmulator
    $grupos = @{
        'ImpressaoOPs-Consulta' = (Get-ADUser -Identity ($ContaExecutor.Split('\')[-1]) -Server $dc)
        'ImpressaoOPs-Operacao' = (Get-ADUser -Identity ($ContaOperadora.Split('\')[-1]) -Server $dc)
    }
    foreach ($nome in $grupos.Keys) {
        $grupo = Get-ADGroup -Filter { SamAccountName -eq $nome } -Server $dc -Properties member
        if (-not $grupo) {
            $grupo = New-ADGroup -Name $nome -SamAccountName $nome -GroupScope Global -GroupCategory Security -Path $dominio.UsersContainer -Server $dc -PassThru
        }
        if ($grupo.GroupCategory -ne 'Security') { throw "O grupo $nome precisa ser de seguranca." }
        if ($grupos[$nome].DistinguishedName -notin $grupo.member) {
            Add-ADGroupMember -Identity $grupo -Members $grupos[$nome] -Server $dc
        }
    }

    foreach ($item in $sites) {
        $nome = $item.Nome
        $pool = $iis.ApplicationPools[$nome]
        if (-not $pool) {
            $pool = $iis.ApplicationPools.Add($nome)
            $pool.ManagedRuntimeVersion = ''
            $pool.ManagedPipelineMode = 'Integrated'
            $pool.ProcessModel.IdentityType = 'ApplicationPoolIdentity'
        }
        $pool.AutoStart = $true
        $site = $iis.Sites[$nome]
        if (-not $site) {
            $site = $iis.Sites.Add($nome, 'https', $item.Binding, $item.Caminho)
            $site.ServerAutoStart = $false
            $site.Applications['/'].ApplicationPoolName = $nome
        }
        $binding = $site.Bindings[0]
        $binding.SslFlags = 'Sni'
    }
    $iis.CommitChanges()
} finally { $iis.Dispose() }

# O vinculo IIS e o registro do certificado no HTTP.sys sao etapas distintas.
Import-Module WebAdministration -ErrorAction Stop
foreach ($item in $sites) {
    $vinculos = @(Get-WebBinding -Name $item.Nome -Protocol https -Port $item.Porta -HostHeader $nomeTs |
        Where-Object { $_.bindingInformation -eq $item.Binding -and [int]$_.sslFlags -eq 1 })
    if ($vinculos.Count -ne 1) { throw "Vinculo HTTPS com SNI nao encontrado para $($item.Nome)." }
    $vinculo = $vinculos[0]
    if ($vinculo.certificateHash -ne $cert.Thumbprint -or $vinculo.certificateStoreName -ne 'My') {
        $vinculo.AddSslCertificate($cert.Thumbprint, 'My')
    }
}

# O IIS precisa reconhecer os sites gravados antes de abrir suas secoes por nome.
$iis = [Microsoft.Web.Administration.ServerManager]::new()
try {
    $appHost = $iis.GetApplicationHostConfiguration()
    foreach ($item in $sites) {
        $nome = $item.Nome
        foreach ($secao in 'handlers','security/authorization','security/requestFiltering','httpErrors') {
            $appHost.GetSection("system.webServer/$secao", $nome).OverrideMode = 'Allow'
        }
        foreach ($tipo in 'anonymousAuthentication','windowsAuthentication','basicAuthentication','digestAuthentication') {
            $appHost.GetSection("system.webServer/security/authentication/$tipo", $nome).SetAttributeValue('enabled', ($tipo -eq 'windowsAuthentication'))
        }
        $appHost.GetSection('system.webServer/security/access', $nome).SetAttributeValue('sslFlags', 'Ssl')
        $cgi = $appHost.GetSection('system.webServer/cgi', $nome)
        $cgi.SetAttributeValue('createProcessAsUser', $false)
        $cgi.SetAttributeValue('timeout', [TimeSpan]::FromSeconds($item.Tempo))
    }
    $iis.CommitChanges()
} finally { $iis.Dispose() }

function Set-PermissaoOps($Caminho, $Contas, $Direitos, [switch]$Pasta, [switch]$Privado) {
    $acl = Get-Acl -LiteralPath $Caminho
    $heranca = if ($Pasta) { 'ContainerInherit,ObjectInherit' } else { 'None' }
    if ($Privado) {
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($regra in @($acl.Access)) { $acl.RemoveAccessRuleSpecific($regra) }
        foreach ($sid in 'S-1-5-18','S-1-5-32-544') {
            $admin = [Security.Principal.SecurityIdentifier]::new($sid)
            $acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($admin, 'FullControl', $heranca, 'None', 'Allow'))
        }
    }
    foreach ($nomeConta in @($Contas)) {
        $identidade = [Security.Principal.NTAccount]::new($nomeConta)
        $acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identidade, $Direitos, $heranca, 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $Caminho -AclObject $acl
}

foreach ($item in $sites) {
    Set-PermissaoOps $item.Caminho $item.Pool ReadAndExecute -Pasta
    Set-PermissaoOps (Split-Path -Parent $item.Exe) $item.Pool ReadAndExecute -Pasta
    $pastaPrivada = Split-Path -Parent $item.Arquivo
    $null = [IO.Directory]::CreateDirectory($pastaPrivada)
    $leitores = if ($item.Nome -eq 'ImpressaoOpsPortal') { @($item.Pool, $ContaExecutor) } else { @($item.Pool) }
    Set-PermissaoOps $pastaPrivada $leitores ReadAndExecute -Pasta -Privado
    if (Test-Path -LiteralPath $item.Arquivo -PathType Leaf) { Set-PermissaoOps $item.Arquivo $leitores Read -Privado }
}
if (-not $bancoJaExiste) {
    [IO.File]::Copy((Resolve-Path -LiteralPath $origemBanco).ProviderPath, $configBanco, $false)
    Set-PermissaoOps $configBanco 'IIS AppPool\NunesApiSisplan' Read -Privado
}
if (-not (Test-Path -LiteralPath $configPortal -PathType Leaf)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    @{
        origem = $origemPortal; porta_executor = $PortaExecutor; porta_api = $PortaApi
        segredo = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    } | ConvertTo-Json | Out-File -LiteralPath $configPortal -Encoding ascii -NoClobber
}
$pastaExecutor = Split-Path -Parent $programa
Set-PermissaoOps $pastaExecutor $ContaExecutor ReadAndExecute -Pasta
$logExecutor = Join-Path $pastaExecutor 'impressao.log'
if (-not (Test-Path -LiteralPath $logExecutor -PathType Leaf)) { New-Item -ItemType File -Path $logExecutor | Out-Null }
Set-PermissaoOps $logExecutor $ContaExecutor Modify

if ($RedePermitida) {
    foreach ($item in $sites) {
        $regra = "Nunes-$($item.Nome)-HTTPS"
        if (-not (Get-NetFirewallRule -Name $regra -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -Name $regra -DisplayName $regra -Direction Inbound -Action Allow -Protocol TCP -LocalPort $item.Porta -RemoteAddress $RedePermitida -Profile Domain | Out-Null
        }
    }
}
Set-Service W3SVC -StartupType Automatic
Start-Service W3SVC
$iis = [Microsoft.Web.Administration.ServerManager]::new()
try {
    foreach ($item in $sites) {
        $efetiva = $iis.GetWebConfiguration($item.Nome)
        $null = $efetiva.GetSection('system.webServer/handlers').GetCollection()
        $null = $efetiva.GetSection('system.webServer/security/authorization').GetCollection()
        $site = $iis.Sites[$item.Nome]
        if ($site.State -ne 'Started') { $null = $site.Start() }
        $limite = (Get-Date).AddSeconds(8)
        while ($site.State -eq 'Starting' -and (Get-Date) -lt $limite) { Start-Sleep -Milliseconds 250 }
        if ($site.State -ne 'Started') { throw "O site $($item.Nome) nao iniciou." }
        $site.ServerAutoStart = $true
    }
    $iis.CommitChanges()
} finally { $iis.Dispose() }

if (-not $tarefa) {
    $acao = New-ScheduledTaskAction -Execute $programa -Argument $argumentos -WorkingDirectory $pastaExecutor
    $gatilho = New-ScheduledTaskTrigger -AtLogOn -User $ContaExecutor
    $principal = New-ScheduledTaskPrincipal -UserId $ContaExecutor -LogonType Interactive
    $opcoes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho -Principal $principal -Settings $opcoes | Out-Null
}
Write-Output "Sites iniciados. Portal: $origemPortal/"
Write-Output "Tarefa registrada para o proximo logon de $ContaExecutor."
Write-Output 'Se os grupos foram alterados, renove a sessao Windows das contas antes de testar.'
