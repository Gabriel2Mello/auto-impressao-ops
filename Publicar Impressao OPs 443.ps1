#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$Certificado
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ine 'TS01') { throw 'Execute este script no TS01.' }

$nomeSite = 'Nunes-TesteHttpsTs01'
$nomeApp = 'impressao-ops'
$pool = 'ImpressaoOpsPortal'
$raiz = 'C:\Nunes\ImpressaoOpsPortal'
$pastaSite = Join-Path $raiz 'site'
$gateway = Join-Path $raiz 'gateway\PortalOps.exe'
$arquivo = Join-Path $raiz 'privado\portal.json'
$tarefa = 'Nunes Impressao de OPs'
$cert = Get-Item -LiteralPath "Cert:\LocalMachine\My\$Certificado"
if (-not $cert.HasPrivateKey -or $cert.NotBefore -gt (Get-Date) -or
    $cert.NotAfter -le (Get-Date) -or 'ts01' -notin $cert.DnsNameList.Unicode) {
    throw 'Informe um certificado HTTPS valido para ts01 com chave privada.'
}
if ((Get-ScheduledTask -TaskName $tarefa).State -eq 'Running' -or
    (Get-Process -Name 'Impressao OPs' -ErrorAction SilentlyContinue)) {
    throw 'Encerre o executor apos concluir as operacoes antes de publicar.'
}
$config = Get-Content -LiteralPath $arquivo -Raw | ConvertFrom-Json
if ($config.origem -notmatch '^https://(ts01\.gratitude\.local:[0-9]+|ts01)$' -or
    $config.segredo -cnotmatch '^[0-9a-f]{64}$') { throw 'Confira o portal.json existente.' }
[xml]$web = Get-Content -LiteralPath (Join-Path $pastaSite 'web.config') -Raw
$regras = @($web.SelectNodes('/configuration/system.webServer/security/authorization/*'))
if ($regras.Count -ne 2 -or $regras[0].LocalName -ne 'clear' -or
    $regras[1].LocalName -ne 'add' -or $regras[1].accessType -ne 'Allow' -or
    $regras[1].roles -ne 'GRATITUDE\ImpressaoOPs-Operacao' -or $regras[1].users -or
    $web.configuration.'system.webServer'.handlers.add.scriptProcessor -ne $gateway -or
    -not (Test-Path -LiteralPath $gateway -PathType Leaf)) {
    throw 'Confira o pacote atualizado do portal e as regras de autorizacao.'
}

Import-Module WebAdministration
Add-Type -Path (Join-Path $env:windir 'System32\inetsrv\Microsoft.Web.Administration.dll')
$iis = [Microsoft.Web.Administration.ServerManager]::new()
try {
    if (-not $iis.ApplicationPools[$pool]) { throw 'Instale primeiro o portal na porta original.' }
    $site = $iis.Sites[$nomeSite]
    foreach ($outro in $iis.Sites) {
        if ($outro.Name -ne $nomeSite -and @($outro.Bindings | Where-Object {
            $_.Protocol -eq 'https' -and $_.BindingInformation -match ':443:ts01$'
        }).Count) { throw "O nome ts01 na porta 443 ja pertence a $($outro.Name)." }
    }
    if (-not $site) {
        $pastaTeste = 'C:\Nunes\TesteHttpsTs01'
        $null = [IO.Directory]::CreateDirectory($pastaTeste)
        $site = $iis.Sites.Add($nomeSite, 'https', '*:443:ts01', $pastaTeste)
        $site.ServerAutoStart = $false
        $site.Bindings[0].SslFlags = 'Sni'
    }
    if ($site.Bindings.Count -ne 1 -or $site.Bindings[0].Protocol -ne 'https' -or
        $site.Bindings[0].BindingInformation -ne '*:443:ts01' -or
        $site.Bindings[0].SslFlags -ne 'Sni') { throw 'Confira o vinculo do site HTTPS de teste.' }
    $app = $site.Applications["/$nomeApp"]
    if (-not $app) {
        $app = $site.Applications.Add("/$nomeApp", $pastaSite)
        $app.ApplicationPoolName = $pool
    }
    if ($app.ApplicationPoolName -ne $pool -or $app.VirtualDirectories['/'].PhysicalPath -ne $pastaSite) {
        throw 'A aplicacao ja existe com outra configuracao.'
    }
    $iis.CommitChanges()
} finally { $iis.Dispose() }

$vinculo = Get-WebBinding -Name $nomeSite -Protocol https -Port 443 -HostHeader 'ts01'
if ($vinculo.certificateHash -ne $cert.Thumbprint -or $vinculo.certificateStoreName -ne 'My') {
    $vinculo.AddSslCertificate($cert.Thumbprint, 'My')
}
$iis = [Microsoft.Web.Administration.ServerManager]::new()
try {
    $escopo = "$nomeSite/$nomeApp"
    $appHost = $iis.GetApplicationHostConfiguration()
    foreach ($secao in 'handlers','security/authorization','security/requestFiltering','httpErrors') {
        $appHost.GetSection("system.webServer/$secao", $escopo).OverrideMode = 'Allow'
    }
    foreach ($tipo in 'anonymousAuthentication','windowsAuthentication','basicAuthentication','digestAuthentication') {
        $appHost.GetSection("system.webServer/security/authentication/$tipo", $escopo).
            SetAttributeValue('enabled', ($tipo -eq 'windowsAuthentication'))
    }
    $appHost.GetSection('system.webServer/security/access', $escopo).SetAttributeValue('sslFlags', 'Ssl')
    $cgi = $appHost.GetSection('system.webServer/cgi', $escopo)
    $cgi.SetAttributeValue('createProcessAsUser', $false)
    $cgi.SetAttributeValue('timeout', [TimeSpan]::FromSeconds(35))
    $restricoes = $appHost.GetSection('system.webServer/security/isapiCgiRestriction').GetCollection()
    $entrada = $restricoes | Where-Object { $_.GetAttributeValue('path') -eq $gateway } | Select-Object -First 1
    if (-not $entrada) {
        $entrada = $restricoes.CreateElement('add')
        $entrada.SetAttributeValue('path', $gateway)
        $entrada.SetAttributeValue('description', 'Nunes Impressao de OPs')
        $restricoes.Add($entrada)
    }
    $entrada.SetAttributeValue('allowed', $true)
    $iis.Sites[$nomeSite].ServerAutoStart = $true
    $iis.CommitChanges()
    $site = $iis.Sites[$nomeSite]
    if ($site.State -ne 'Started') { $null = $site.Start() }
} finally { $iis.Dispose() }

if ($config.origem -ne 'https://ts01') {
    $config.origem = 'https://ts01'
    [IO.File]::WriteAllText($arquivo, ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
}
Start-ScheduledTask -TaskName $tarefa
Write-Output 'Portal publicado em https://ts01/impressao-ops/. Valide com a conta operadora.'
