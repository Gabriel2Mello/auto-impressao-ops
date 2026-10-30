$ErrorActionPreference = 'Stop'
$destinoImpressao = Join-Path $PSScriptRoot 'Impressao OPs.exe'
$argumentosImpressao = @()
if (-not (Test-Path -LiteralPath $destinoImpressao -PathType Leaf)) {
    $destinoImpressao = Join-Path $PSScriptRoot '.venv-desktop\Scripts\python.exe'
    $argumentosImpressao = @((Join-Path $PSScriptRoot 'impressao.py'))
}
if (-not (Test-Path -LiteralPath $destinoImpressao -PathType Leaf)) { throw 'Prepare o ambiente desktop conforme DESKTOP.md.' }
& $destinoImpressao @argumentosImpressao --criar-atalho (Join-Path $PSScriptRoot 'Abrir Impressao OPs.lnk')
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o atalho desktop.' }
Write-Output 'Atalho desktop criado na pasta do projeto.'
