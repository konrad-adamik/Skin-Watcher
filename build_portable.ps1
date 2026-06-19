$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$buildRoot = Join-Path $root "build\portable"
$distRoot = Join-Path $root "dist"
$portableDir = Join-Path $distRoot "SkinWatcher"
$zipPath = Join-Path $distRoot "SkinWatcher-portable.zip"
$browserCache = Join-Path $buildRoot "playwright-browsers"
$workerDist = Join-Path $buildRoot "worker-dist"
$workerDir = Join-Path $portableDir "worker"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The project virtual environment is missing. Run start.bat once, then retry."
}

foreach ($path in @($buildRoot, $portableDir, $zipPath)) {
    $fullPath = [System.IO.Path]::GetFullPath($path)
    if (-not $fullPath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a path outside the project: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

Write-Host "Installing the portable-build dependency..."
& $python -m pip install "pyinstaller>=6.16,<7"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller installation failed."
}

Write-Host "Downloading the bundled Chromium build..."
$previousBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
$env:PLAYWRIGHT_BROWSERS_PATH = $browserCache
try {
    & $python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright Chromium installation failed."
    }
}
finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $previousBrowserPath
}

Write-Host "Building SkinWatcher.exe..."
$guiArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", "SkinWatcher",
    "--icon", (Join-Path $root "assets\skinwatcher.ico"),
    "--add-data", "$root\assets;assets",
    "--distpath", $distRoot,
    "--workpath", (Join-Path $buildRoot "gui-work"),
    "--specpath", (Join-Path $buildRoot "spec"),
    (Join-Path $root "main.py")
)
& $python -m PyInstaller @guiArgs
if ($LASTEXITCODE -ne 0) {
    throw "SkinWatcher GUI build failed."
}

Write-Host "Building the hidden watcher worker..."
$workerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--console",
    "--name", "SkinWatcherWorker",
    "--icon", (Join-Path $root "assets\skinwatcher.ico"),
    "--collect-all", "playwright",
    "--distpath", $workerDist,
    "--workpath", (Join-Path $buildRoot "worker-work"),
    "--specpath", (Join-Path $buildRoot "spec"),
    (Join-Path $root "worker.py")
)
& $python -m PyInstaller @workerArgs
if ($LASTEXITCODE -ne 0) {
    throw "SkinWatcher worker build failed."
}

New-Item -ItemType Directory -Path $workerDir -Force | Out-Null
Copy-Item -Path (Join-Path $workerDist "SkinWatcherWorker\*") -Destination $workerDir -Recurse -Force
Copy-Item -LiteralPath $browserCache -Destination (Join-Path $portableDir "playwright-browsers") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root "PORTABLE_README.txt") -Destination $portableDir -Force

Write-Host "Creating portable ZIP..."
Compress-Archive -Path $portableDir -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Portable build ready:"
Write-Host "  Folder: $portableDir"
Write-Host "  ZIP:    $zipPath"
