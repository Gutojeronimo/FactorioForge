$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:DOTNET_CLI_HOME = Join-Path $PSScriptRoot '.runtime/dotnet'
$env:NUGET_PACKAGES = Join-Path $PSScriptRoot '.runtime/nuget'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = 'false'
dotnet build desktop/ForgePlan.Desktop.csproj -c Release -o app-next --nologo -v quiet -p:RestoreIgnoreFailedSources=true
if ($LASTEXITCODE -ne 0) { throw 'A compilação do ForgePlan falhou.' }
