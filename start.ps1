$ErrorActionPreference = 'Stop'
$desktopExe = Join-Path $PSScriptRoot 'app/ForgePlan.exe'
if (-not (Test-Path -LiteralPath $desktopExe)) { throw 'Execute build.ps1 para compilar o aplicativo Windows.' }
Start-Process -FilePath $desktopExe -WorkingDirectory $PSScriptRoot
