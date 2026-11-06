$ErrorActionPreference = 'Stop'
# Same rule as ForgePlan.cmd: the build output (app-next) wins over the older app folder.
$desktopExe = Join-Path $PSScriptRoot 'app-next/ForgePlan.exe'
if (-not (Test-Path -LiteralPath $desktopExe)) { $desktopExe = Join-Path $PSScriptRoot 'app/ForgePlan.exe' }
if (-not (Test-Path -LiteralPath $desktopExe)) { throw 'Execute build.ps1 para compilar o aplicativo Windows.' }
Start-Process -FilePath $desktopExe -WorkingDirectory $PSScriptRoot
