$ErrorActionPreference = 'Stop'
& "$env:RUNNER_TEMP\vcpkg\vcpkg.exe" install tesseract "--triplet=$env:TRIPLET" --disable-metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
