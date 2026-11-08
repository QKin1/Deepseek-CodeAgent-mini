$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
$env:PYTHONPATH = "$root\src;$root\.qt-packages;$root\.packages"
$env:PYTHONNOUSERSITE = '1'

Push-Location $root
try {
    & $python -S -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name CodeAgent `
        --paths "$root\src" `
        --paths "$root\.qt-packages" `
        --paths "$root\.packages" `
        "$root\src\code_agent\main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    Write-Host "Built: $root\dist\CodeAgent.exe"
}
finally {
    Pop-Location
}
