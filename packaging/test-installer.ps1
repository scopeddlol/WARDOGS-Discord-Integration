param([string]$Installer = 'dist\WARDOGS-Discord-Setup.exe')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
$testRoot = Join-Path $repoRoot ('artifacts\install-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $testRoot | Out-Null
$installPath = Join-Path $testRoot 'app'
$env:WARDOGS_DATA_DIR = Join-Path $testRoot 'data'
$env:QT_QPA_PLATFORM = 'offscreen'
# Prevent the developer's external OCR override from hiding a broken bundle.
Remove-Item Env:TESSERACT_CMD -ErrorAction SilentlyContinue
$installerPath = (Resolve-Path $Installer).Path
function Run-Checked([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(120000)) { $process.Kill(); throw "Timed out: $Executable" }
    if ($process.ExitCode -ne 0) { throw "Failed with exit $($process.ExitCode): $Executable" }
}
$installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/TASKS=""', '/GROUP="WARDOGS Discord Test"', ('/DIR="' + $installPath + '"'))
try {
    Run-Checked $installerPath $installArgs
    Run-Checked (Join-Path $installPath 'WARDOGS Discord.exe') @('--smoke-test', ('"' + (Join-Path $testRoot 'first-launch') + '"'))
    $first = Get-Content (Join-Path $testRoot 'first-launch\smoke.json') -Raw | ConvertFrom-Json
    if (!$first.ok) { throw 'Installed application smoke test failed.' }
    $sentinel = Join-Path $env:WARDOGS_DATA_DIR 'upgrade-check.txt'
    Set-Content $sentinel 'preserve user data'
    Run-Checked $installerPath $installArgs
    if ((Get-Content $sentinel) -ne 'preserve user data') { throw 'Upgrade lost per-user data.' }
    Run-Checked (Join-Path $installPath 'WARDOGS Discord.exe') @('--smoke-test', ('"' + (Join-Path $testRoot 'after-upgrade') + '"'))
    $second = Get-Content (Join-Path $testRoot 'after-upgrade\smoke.json') -Raw | ConvertFrom-Json
    if (!$second.ok) { throw 'Upgrade smoke test failed.' }
} finally {
    $uninstaller = Join-Path $installPath 'unins000.exe'
    if (Test-Path $uninstaller) { Run-Checked $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') }
}
if (Test-Path (Join-Path $installPath 'WARDOGS Discord.exe')) { throw 'Uninstall left the application executable.' }
Write-Output "Install, GUI/OCR, upgrade, and uninstall passed. Evidence: $testRoot"
