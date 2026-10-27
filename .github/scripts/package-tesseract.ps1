$ErrorActionPreference = 'Stop'
$installed = Join-Path $env:RUNNER_TEMP "vcpkg\installed\$env:TRIPLET"
$binary = Get-ChildItem $installed -Filter 'tesseract.exe' -File -Recurse | Select-Object -First 1
if ($null -eq $binary) {
  throw "Could not find the Tesseract executable in $installed"
}

New-Item -ItemType Directory -Force -Path bundle, dist | Out-Null
Copy-Item $binary.FullName bundle/
$binDirectory = Join-Path $installed 'bin'
if (Test-Path $binDirectory) {
  Copy-Item (Join-Path $binDirectory '*') bundle/ -Recurse -Force
}
Compress-Archive -Path 'bundle/*' -DestinationPath "dist/tesseract-$env:TRIPLET.zip" -Force
