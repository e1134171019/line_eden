[CmdletBinding()]
param(
    [switch]$NoGemini
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = Join-Path $ProjectRoot ".venv/Scripts/python.exe"

if (-not (Test-Path $PythonPath)) {
    throw "找不到虛擬環境 Python：$PythonPath"
}

$Arguments = @("-m", "src.automation.scheduled_runner")
if ($NoGemini) {
    $Arguments += "--no-gemini"
}

Push-Location $ProjectRoot
try {
    & $PythonPath @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
