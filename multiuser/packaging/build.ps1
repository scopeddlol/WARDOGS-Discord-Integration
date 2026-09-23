param([string]$Python = '.\.venv\Scripts\python.exe', [string]$ISCC = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python packaging/collect-licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
& $Python -m PyInstaller --noconfirm packaging/agent.spec
if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
& $ISCC packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
$hash = (Get-FileHash dist/WARDOGS-Agent-Setup.exe -Algorithm SHA256).Hash.ToLower()
"$hash  WARDOGS-Agent-Setup.exe" | Set-Content -Encoding ascii dist/SHA256SUMS.txt
