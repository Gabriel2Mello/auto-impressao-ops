param([string]$Python = (Join-Path $PSScriptRoot '.venv-desktop\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
& $Python -m PyInstaller --noconfirm --clean --distpath "$PSScriptRoot\dist" --workpath "$PSScriptRoot\build" "$PSScriptRoot\Impressao OPs.spec"
if ($LASTEXITCODE -ne 0) { throw 'O build desktop da Impressão de OPs falhou.' }
$pacoteImpressao = Join-Path $PSScriptRoot 'dist\Impressao OPs'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'DESKTOP.md') -Destination $pacoteImpressao
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Abrir Impressao OPs.cmd') -Destination $pacoteImpressao
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Criar Atalho Impressao OPs.ps1') -Destination $pacoteImpressao
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Testar Interface Impressao OPs.cmd') -Destination $pacoteImpressao
Write-Output "Pacote gerado em $pacoteImpressao. Distribua a pasta inteira, incluindo _internal."
