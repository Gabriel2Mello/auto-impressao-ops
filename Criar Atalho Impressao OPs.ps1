$ErrorActionPreference = 'Stop'
$destinoImpressao = $null
foreach ($ambienteImpressao in @('.venv', 'venv32')) {
    $pythonImpressao = Join-Path $PSScriptRoot "$ambienteImpressao\Scripts\pythonw.exe"
    if (Test-Path -LiteralPath $pythonImpressao -PathType Leaf) {
        $destinoImpressao = $pythonImpressao
        break
    }
}
if (-not $destinoImpressao) { throw 'Instale o ambiente Python conforme o README.md.' }
$shellImpressao = New-Object -ComObject WScript.Shell
$atalhoImpressao = $shellImpressao.CreateShortcut((Join-Path $PSScriptRoot 'Abrir Impressao OPs.lnk'))
$atalhoImpressao.TargetPath = $destinoImpressao
$atalhoImpressao.Arguments = '"' + (Join-Path $PSScriptRoot 'impressao.py') + '"'
$atalhoImpressao.WorkingDirectory = $PSScriptRoot
$atalhoImpressao.IconLocation = (Join-Path $PSScriptRoot 'icons\icone.ico') + ',0'
$atalhoImpressao.Description = 'Imprimir ordens de produção por intervalo ou lista'
$atalhoImpressao.Save()
Write-Output 'Atalho criado na pasta do projeto com o ícone Nunes.'
