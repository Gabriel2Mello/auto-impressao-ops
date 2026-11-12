param([string]$Python = (Join-Path $PSScriptRoot '.venv-desktop\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'

& $Python -c 'import struct, sys, PyInstaller; sys.exit(struct.calcsize(chr(80)) != 4)'
if ($LASTEXITCODE -ne 0) { throw 'Use o ambiente desktop com PyInstaller e Python de 32 bits.' }

$entregaOps = Join-Path $PSScriptRoot ('.local\entregas\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-portal-ts01')
$distOps = Join-Path $entregaOps 'dist'
$workOps = Join-Path $entregaOps 'work'
$pacoteOps = Join-Path $entregaOps 'pacote'
$portalOps = Join-Path $pacoteOps 'ImpressaoOpsPortal'
if (Test-Path -LiteralPath $entregaOps) { throw 'O caminho desta entrega ja existe.' }
New-Item -ItemType Directory -Path $entregaOps | Out-Null
Write-Output "Diretorio da entrega: $entregaOps"

Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath $distOps --workpath $workOps 'Impressao OPs.spec' -- --portal
    if ($LASTEXITCODE -ne 0) { throw 'Build do executor falhou.' }
    & $Python -m PyInstaller --noconfirm --onedir --console --name PortalOps --distpath $distOps --workpath $workOps --specpath $entregaOps portal_ops_cgi.py
    if ($LASTEXITCODE -ne 0) { throw 'Build do gateway falhou.' }
    $siteOps = Join-Path $portalOps 'site'
    New-Item -ItemType Directory -Path $siteOps | Out-Null
    Copy-Item -Recurse -LiteralPath (Join-Path $distOps 'Impressao OPs') -Destination (Join-Path $portalOps 'executor')
    Copy-Item -Recurse -LiteralPath (Join-Path $distOps 'PortalOps') -Destination (Join-Path $portalOps 'gateway')
    Copy-Item -LiteralPath 'iis-portal-ops\web.config' -Destination $siteOps
    Copy-Item -LiteralPath 'PORTAL-TS01.md', 'Instalar Impressao OPs TS01.ps1' -Destination $portalOps
    $zipOps = Join-Path $entregaOps 'Impressao de OPs - Portal TS01.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($pacoteOps, $zipOps, [IO.Compression.CompressionLevel]::Optimal, $false)
    Get-FileHash -LiteralPath $zipOps -Algorithm SHA256 | Format-List
}
finally {
    Pop-Location
}
