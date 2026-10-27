$ErrorActionPreference = 'Stop'
& "$env:RUNNER_TEMP\vcpkg\bootstrap-vcpkg.bat" -disableMetrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
