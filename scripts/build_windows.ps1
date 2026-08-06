param(
    [switch]$Clean,
    [switch]$SkipTests,
    [switch]$SkipPackage
)

try {
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PortableDistRoot = "$ProjectRoot\portable-dist"
Set-Location $ProjectRoot

function Assert-LastExitCode([string]$Operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Remove-BuildDirectory([string]$Directory) {
    if (-not (Test-Path $Directory)) { return }
    $ResolvedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    $ResolvedTarget = [IO.Path]::GetFullPath($Directory).TrimEnd('\') + '\'
    if (-not $ResolvedTarget.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the project: $Directory"
    }
    Remove-Item $Directory -Recurse -Force
}

function Compress-PortableArchiveWithRetry(
    [string]$SourcePath,
    [string]$DestinationPath
) {
    $MaximumAttempts = 6
    for ($Attempt = 1; $Attempt -le $MaximumAttempts; $Attempt++) {
        try {
            if (Test-Path $DestinationPath) {
                Remove-Item $DestinationPath -Force
            }
            Compress-Archive `
                -Path $SourcePath `
                -DestinationPath $DestinationPath `
                -CompressionLevel Optimal
            return
        } catch {
            if ($Attempt -eq $MaximumAttempts) {
                throw
            }
            Write-Warning (
                "Portable packaging attempt $Attempt failed; retrying after a transient file lock. " +
                $_.Exception.Message
            )
            Start-Sleep -Seconds 2
        }
    }
}

if ($Clean) {
    Remove-BuildDirectory "$ProjectRoot\build"
    Remove-BuildDirectory $PortableDistRoot
}

if (-not (Test-Path "$ProjectRoot\.venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv "$ProjectRoot\.venv"
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv "$ProjectRoot\.venv"
    } else {
        throw "Python 3 was not found. Use the included GitHub Actions workflow or build on a Windows computer with Python 3.11 or newer."
    }
    Assert-LastExitCode "Virtual-environment creation"
}

$Python = "$ProjectRoot\.venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
Assert-LastExitCode "pip upgrade"
& $Python -m pip install -r "$ProjectRoot\requirements-dev.txt"
Assert-LastExitCode "Dependency installation"

$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "$ProjectRoot\src"
try {
    if (-not $SkipTests) {
        & $Python -m unittest discover -s "$ProjectRoot\tests" -v
        Assert-LastExitCode "Automated tests"
    }

    $Version = (& $Python -c "from traffic_crash_notebook import __version__; print(__version__)").Trim()
    Assert-LastExitCode "Version lookup"

    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name TrafficCrashNotebook `
        --splash "$ProjectRoot\assets\windows\TrafficCrashNotebookSplash.png" `
        --icon "$ProjectRoot\assets\windows\TrafficCrashNotebook.ico" `
        --manifest "$ProjectRoot\assets\windows\TrafficCrashNotebook.manifest" `
        --distpath "$PortableDistRoot" `
        --paths "$ProjectRoot\src" `
        --add-data "$ProjectRoot\assets;assets" `
        --collect-data spellchecker `
        "$ProjectRoot\run_app.py"
    Assert-LastExitCode "PyInstaller build"
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}

$ApplicationFolder = "$PortableDistRoot\TrafficCrashNotebook"
$Executable = "$ApplicationFolder\TrafficCrashNotebook.exe"
if (-not (Test-Path $Executable)) {
    throw "The portable executable was not created: $Executable"
}
& $Python "$ProjectRoot\scripts\verify_windows_executable_manifest.py" "$Executable"
Assert-LastExitCode "Windows executable manifest verification"

Copy-Item "$ProjectRoot\README.md" "$ApplicationFolder\README.txt" -Force
Copy-Item "$ProjectRoot\docs\PORTABLE_WINDOWS.txt" "$ApplicationFolder\START_HERE.txt" -Force
Copy-Item "$ProjectRoot\docs\PYSPELLCHECKER_LICENSE.txt" "$ApplicationFolder\PYSPELLCHECKER_LICENSE.txt" -Force
Copy-Item "$ProjectRoot\scripts\verify_portable_windows.ps1" "$ApplicationFolder\VERIFY_PORTABLE.ps1" -Force
Copy-Item "$ProjectRoot\scripts\VERIFY_PORTABLE.bat" "$ApplicationFolder\VERIFY_PORTABLE.bat" -Force

$BuildMoment = Get-Date
$BuildTime = $BuildMoment.ToString("MM/dd/yyyy HH:mm:ss zzz")
$BuildId = "$Version-$($BuildMoment.ToString('yyyyMMdd-HHmmss'))"
$PythonVersion = (& $Python --version 2>&1).ToString().Trim()
@(
    "Traffic Crash Notebook $Version"
    "Portable Windows x64 build"
    "Build ID: $BuildId"
    "Built: $BuildTime"
    "Build runtime: $PythonVersion"
    "No installer or administrator rights are required on the target computer."
) | Set-Content "$ApplicationFolder\BUILD_INFO.txt" -Encoding UTF8

$SelfTestDirectory = "$ProjectRoot\build\portable-self-test"
Remove-BuildDirectory $SelfTestDirectory
New-Item -ItemType Directory -Path $SelfTestDirectory -Force | Out-Null
$Process = Start-Process -FilePath $Executable `
    -ArgumentList "--self-test", "`"$SelfTestDirectory`"" `
    -WindowStyle Hidden `
    -Wait -PassThru
if ($Process.ExitCode -ne 0) {
    $FailureLog = "$SelfTestDirectory\portable_self_test.txt"
    if (Test-Path $FailureLog) { Get-Content $FailureLog | Write-Host }
    throw "The finished executable failed its portable self-test with exit code $($Process.ExitCode)."
}
$SelfTestLog = "$SelfTestDirectory\portable_self_test.txt"
if (-not (Test-Path $SelfTestLog) -or -not (Select-String -Path $SelfTestLog -Pattern "^PASS$" -Quiet)) {
    throw "The finished executable did not produce a passing self-test log."
}

Write-Host "Portable executable self-test: PASS"
if (-not $SkipPackage) {
    $ReleaseDirectory = "$ProjectRoot\release"
    New-Item -ItemType Directory -Path $ReleaseDirectory -Force | Out-Null
    $Archive = "$ReleaseDirectory\TrafficCrashNotebook-$Version-Windows-Portable.zip"
    Compress-PortableArchiveWithRetry $ApplicationFolder $Archive
    $Hash = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
    "$Hash *$(Split-Path -Leaf $Archive)" | Set-Content "$Archive.sha256.txt" -Encoding ASCII
    & $Python "$ProjectRoot\scripts\generate_release_manifests.py" `
        --project-root "$ProjectRoot" `
        --version "$Version" `
        --archive "$Archive" `
        --build-info "$ApplicationFolder\BUILD_INFO.txt" `
        --release-notes "$ProjectRoot\docs\RELEASE_NOTES.md" `
        --output-directory "$ReleaseDirectory"
    Assert-LastExitCode "Release-manifest generation"
    & $Python "$ProjectRoot\scripts\verify_release_assets.py" `
        --manifest "$ReleaseDirectory\update-manifest.json" `
        --archive "$Archive" `
        --files "$ReleaseDirectory\TrafficCrashNotebook-$Version-Windows-Portable.files.json"
    Assert-LastExitCode "Release-manifest verification"
    Write-Host "Portable package created at:"
    Write-Host $Archive
    Write-Host "SHA-256: $Hash"
} else {
    Write-Host "Portable application created at:"
    Write-Host $Executable
}
} catch {
    Write-Error $_
    exit 1
}
exit 0
