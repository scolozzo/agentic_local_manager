$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$repoRoot\tools\install_windows.py"
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$repoRoot\tools\install_windows.py"
    exit $LASTEXITCODE
}

Write-Error "No se encontro Python en PATH. Instala Python 3 antes de ejecutar el instalador."
