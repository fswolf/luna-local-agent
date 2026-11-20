# Luna, download and go (Windows). The first run fetches uv (a small tool
# from astral.sh) into %LOCALAPPDATA%\Luna, uv fetches a private Python 3.12,
# and app\bootstrap.py does the rest in a setup window. Nothing system-wide,
# no admin. Later runs start her straight away.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'      # Invoke-WebRequest's progress bar slows it to a crawl
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $env:LOCALAPPDATA 'Luna'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$env:UV_PYTHON_INSTALL_DIR = Join-Path $data 'python'
$env:UV_CACHE_DIR = Join-Path $data 'cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'

function Stop-Luna($why) {
    Write-Host "Luna couldn't start: $why" -ForegroundColor Red
    exit 1
}

$uvDir = Join-Path $data 'uv'
$uv = Join-Path $uvDir 'uv.exe'
if (-not (Test-Path $uv)) {
    Write-Host 'Getting Luna ready for the first time (a minute or two)...'
    $target = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64-pc-windows-msvc' } else { 'x86_64-pc-windows-msvc' }
    $url = "https://github.com/astral-sh/uv/releases/latest/download/uv-$target.zip"
    $zip = Join-Path $data 'uv.zip'
    $tmp = Join-Path $data 'uv.tmp'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $found = Get-ChildItem -Path $tmp -Recurse -Filter 'uv.exe' | Select-Object -First 1
        if (-not $found) { throw 'uv.exe not in the download' }
        if (Test-Path $uvDir) { Remove-Item -Recurse -Force $uvDir }
        Move-Item -Path $found.DirectoryName -Destination $uvDir
    } catch {
        Stop-Luna "couldn't download uv from $url (no internet?) - $_"
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $zip
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tmp
    }
}

$venv = Join-Path $data 'venv'
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host "Getting Luna's own Python (first run only)..."
    if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }   # half-made by a run that was stopped
    & $uv venv --quiet --python 3.12 --seed $venv
    if ($LASTEXITCODE -ne 0) { Stop-Luna "couldn't make her Python (no internet?)" }
}

# pythonw: no console window behind her. --no-window prints the setup page's
# address, so it keeps python.exe and this window.
$bootstrap = Join-Path $root 'app\bootstrap.py'
if ($args -contains '--no-window') {
    & $py $bootstrap @args
    exit $LASTEXITCODE
}
$pyw = Join-Path $venv 'Scripts\pythonw.exe'
$argv = @("`"$bootstrap`"") + $args
Start-Process -FilePath $pyw -ArgumentList $argv -WorkingDirectory $root
