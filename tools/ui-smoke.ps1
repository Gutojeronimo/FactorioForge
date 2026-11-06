# Smoke test da janela do ForgePlan: abre o app, captura a janela e valida tamanho/erros.
param(
  [string]$Exe = 'app-next/ForgePlan.exe',
  [string]$Out = '.runtime/ui-smoke.png',
  [int]$Wait = 20
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not [System.IO.Path]::IsPathRooted($Exe)) { $Exe = Join-Path $root $Exe }
if (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $root $Out }
if (-not (Test-Path -LiteralPath $Exe)) { Write-Host "FALHA: executavel nao encontrado: $Exe"; exit 1 }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SmokeWin {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@

$errLog = Join-Path $root '.runtime/desktop-error.log'
$errBefore = $null
if (Test-Path -LiteralPath $errLog) { $errBefore = (Get-Item -LiteralPath $errLog).LastWriteTimeUtc }

$exit = 0
$p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path -Parent (Split-Path -Parent $Exe)) -PassThru
try {
  $handle = [IntPtr]::Zero
  for ($i = 0; $i -lt $Wait; $i++) {
    Start-Sleep -Seconds 1
    $p.Refresh()
    if ($p.HasExited) { break }
    if ($p.MainWindowHandle -ne [IntPtr]::Zero) { $handle = $p.MainWindowHandle; break }
  }
  if ($p.HasExited) { Write-Host "FALHA: o processo terminou (codigo $($p.ExitCode))."; $exit = 1 }
  elseif ($handle -eq [IntPtr]::Zero) { Write-Host "FALHA: nenhuma janela em $Wait s."; $exit = 1 }
  else {
    Start-Sleep -Seconds 3
    $p.Refresh()
    if ($p.HasExited) { Write-Host "FALHA: o processo terminou (codigo $($p.ExitCode))."; $exit = 1 }
    else {
      $handle = $p.MainWindowHandle
      $r = New-Object SmokeWin+RECT
      [SmokeWin]::GetWindowRect($handle, [ref]$r) | Out-Null
      $w = $r.R - $r.L; $h = $r.B - $r.T
      if ($w -lt 1000 -or $h -lt 600) { Write-Host "FALHA: janela pequena demais ($w x $h)."; $exit = 1 }
      else {
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $dc = $g.GetHdc()
        [SmokeWin]::PrintWindow($handle, $dc, 2) | Out-Null
        $g.ReleaseHdc($dc); $g.Dispose()
        $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
        Write-Host "PNG: $Out ($w x $h)"
        # A captura por PrintWindow pode sair em branco em sessoes sem composicao WPF; a arvore de UI Automation confirma os controles.
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        $names = @(); foreach ($e in $all) { $names += $e.Current.Name }
        Write-Host "Controles na arvore de UI: $($all.Count)"
        foreach ($need in 'Arquivo', 'Produtos') { if ($names -notcontains $need) { Write-Host "FALHA: controle '$need' ausente."; $exit = 1 } }
      }
    }
  }
  if (Test-Path -LiteralPath $errLog) {
    $now = (Get-Item -LiteralPath $errLog).LastWriteTimeUtc
    if ($null -eq $errBefore -or $now -ne $errBefore) { Write-Host "FALHA: $errLog foi criado/alterado durante o teste."; $exit = 1 }
  }
} finally {
  try {
    if (-not $p.HasExited) {
      $p.CloseMainWindow() | Out-Null
      if (-not $p.WaitForExit(3000)) { Stop-Process -Id $p.Id -Force }
    }
  } catch { }
}
if ($exit -eq 0) { Write-Host 'OK' }
exit $exit
