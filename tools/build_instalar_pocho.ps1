$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outputExe = Join-Path $repoRoot "InstalarPocho.exe"
$workDir = Join-Path $env:TEMP "InstalarPochoBuild"
$launcherCmd = Join-Path $workDir "launch_installer.cmd"
$sedFile = Join-Path $workDir "installer.sed"

New-Item -ItemType Directory -Force -Path $workDir | Out-Null

$escapedRepoRoot = $repoRoot.Replace('"', '""')
$launcherContent = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$escapedRepoRoot\Instalar_Agentic_Manager.ps1"
"@
Set-Content -Path $launcherCmd -Value $launcherContent -Encoding Ascii

$sedContent = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$outputExe
FriendlyName=InstalarPocho
AppLaunched=launch_installer.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[SourceFiles]
SourceFiles0=$workDir
[SourceFiles0]
%FILE0%= 
[Strings]
FILE0=launch_installer.cmd
"@

Set-Content -Path $sedFile -Value $sedContent -Encoding Ascii

Start-Process -FilePath "$env:SystemRoot\System32\iexpress.exe" -ArgumentList "/N", $sedFile -Wait -NoNewWindow

if (-not (Test-Path $outputExe)) {
    throw "InstalarPocho.exe was not generated."
}

Write-Output "Generated: $outputExe"
