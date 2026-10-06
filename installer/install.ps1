# Install Luna on Windows:   powershell -ExecutionPolicy Bypass -File installer\install.ps1 [--yes] [options]
# Finds Python 3.10-3.13 (3.12 preferred) through the py launcher, offers to
# install 3.12 with winget if there isn't one, then runs installer\install.py.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Find-Python {
    foreach ($v in "3.12", "3.11", "3.13", "3.10") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        }
    }
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p -and $p.Source -notlike "*WindowsApps*") {
        & python -c "import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))"
        if ($LASTEXITCODE -eq 0) { return @("python") }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Luna needs Python 3.10-3.13 (3.12 is best) and none was found."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Install Python 3.12 from https://www.python.org/downloads/ and run this again."
        exit 1
    }
    $yn = Read-Host "Install Python 3.12 with winget? [Y/n]"
    if ($yn -and $yn -notmatch "^[Yy]") { exit 1 }
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Find-Python
    if (-not $py) { Write-Host "Python installed - open a new terminal and run this again."; exit 1 }
}

$exe = $py[0]
$rest = @()
if ($py.Count -gt 1) { $rest = $py[1..($py.Count - 1)] }
& $exe @rest "installer\install.py" @args
exit $LASTEXITCODE
