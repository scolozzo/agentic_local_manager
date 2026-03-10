$ErrorActionPreference = "Stop"

param(
    [switch]$Console
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$scriptPath = if ($Console) { "$repoRoot\tools\install_windows.py" } else { "$repoRoot\tools\install_windows_gui.py" }

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $scriptPath
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $scriptPath
    exit $LASTEXITCODE
}

Write-Error "No se encontro Python en PATH. Instala Python 3 antes de ejecutar el instalador."
