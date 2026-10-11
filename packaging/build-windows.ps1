param(
    [string]$OutputDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) 'build\release\VideoDownloader-windows-x64')
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$expectedOutput = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\release\VideoDownloader-windows-x64'))
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($OutputDirectory -ne $expectedOutput) {
    throw 'Portable rebuilds may replace only this project generated release staging folder.'
}
$pythonPath = Join-Path $projectRoot '.venv-windows\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The approved Windows build environment is missing.'
}
$buildRoot = Join-Path $projectRoot 'build\windows'
New-Item -ItemType Directory -Path $buildRoot, $OutputDirectory -Force | Out-Null
& $pythonPath (Join-Path $PSScriptRoot 'windows-icon.py') (Join-Path $projectRoot 'src\video_downloader\assets\desktop-icon.svg') (Join-Path $buildRoot 'VideoDownloader.ico')
if ($LASTEXITCODE -ne 0) { throw 'Application icon generation failed.' }
$arguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--name', 'VideoDownloader',
    '--distpath', $OutputDirectory, '--workpath', (Join-Path $buildRoot 'work'),
    '--specpath', $buildRoot, '--paths', (Join-Path $projectRoot 'src'),
    '--icon', (Join-Path $buildRoot 'VideoDownloader.ico'),
    '--add-data', ((Join-Path $projectRoot 'src\video_downloader\assets') + ';video_downloader/assets'),
    '--collect-all', 'yt_dlp', '--collect-all', 'yt_dlp_ejs',
    '--collect-all', 'curl_cffi', '--collect-all', 'websockets',
    '--exclude-module', 'PIL',
    (Join-Path $projectRoot 'src\video_downloader\main.py')
)
& $pythonPath @arguments
if ($LASTEXITCODE -ne 0) { throw 'Portable application build failed.' }
# Python 3.12's older MSVC DLLs can shadow Qt's newer runtime at startup.
# The backward-compatible runtime already shipped by the official Qt wheel must
# be placed beside python312.dll, so every bundled component loads the same version.
$qtRuntime = Join-Path $projectRoot '.venv-windows\Lib\site-packages\PySide6'
$payloadRoot = Join-Path $OutputDirectory 'VideoDownloader\_internal'
foreach ($filename in @('VCRUNTIME140.dll', 'VCRUNTIME140_1.dll', 'MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll', 'MSVCP140_ATOMIC_WAIT.dll')) {
    $runtimeSource = Join-Path $qtRuntime $filename
    if (Test-Path -LiteralPath $runtimeSource) {
        Copy-Item -LiteralPath $runtimeSource -Destination (Join-Path $payloadRoot $filename) -Force
    }
}
# Qt uses Windows' native ICU exports. An unrelated ICU 78 DLL found on the
# build host can shadow that OS component and break QtCore in the frozen app.
foreach ($filename in @('icuuc.dll', 'icudt78.dll')) {
    $generatedFile = [System.IO.Path]::GetFullPath((Join-Path $payloadRoot $filename))
    if (-not $generatedFile.StartsWith($payloadRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Generated runtime cleanup escaped the portable payload.'
    }
    if (Test-Path -LiteralPath $generatedFile) {
        Remove-Item -LiteralPath $generatedFile
    }
}
