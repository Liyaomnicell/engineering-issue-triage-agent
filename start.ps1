$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) { $pythonExecutable = $bundledPython }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pythonExecutable = (Get-Command python).Source }
else { throw 'Python 3.11+ is required. Install Python and run: python -m pip install -r requirements.txt' }
& $pythonExecutable (Join-Path $PSScriptRoot 'app.py') @args
