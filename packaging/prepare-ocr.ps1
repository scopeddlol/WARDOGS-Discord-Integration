param([string]$SevenZip = 'C:\Program Files\7-Zip\7z.exe')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$vendorPath = Join-Path $repoRoot 'vendor'
New-Item -ItemType Directory -Force $vendorPath | Out-Null
$archive = Join-Path $vendorPath 'tesseract-setup.exe'
$url = 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe'
$expected = 'C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9'
if (!(Test-Path $archive)) { Invoke-WebRequest $url -OutFile $archive }
if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Tesseract checksum mismatch.' }
if (!(Test-Path $SevenZip)) { throw 'Install 7-Zip or pass -SevenZip with its executable path.' }
$ocrPath = Join-Path $vendorPath 'tesseract'
& $SevenZip x $archive "-o$ocrPath" -y
if ($LASTEXITCODE -ne 0) { throw 'Tesseract extraction failed.' }
& (Join-Path $ocrPath 'tesseract.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Tesseract runtime failed.' }
if (!(Test-Path (Join-Path $ocrPath 'tessdata\eng.traineddata'))) { throw 'Missing English OCR data.' }
