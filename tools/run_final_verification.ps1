$ErrorActionPreference = "Stop"

try {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    $Archive = Join-Path $ProjectRoot "release\TrafficCrashNotebook-0.5.0-Windows-Portable.zip"
    $ChecksumFile = "$Archive.sha256.txt"
    $ExtractRoot = Join-Path $ProjectRoot "build\final-zip-verification-0.5.0-r1"
    $SelfTestRoot = Join-Path $ProjectRoot "build\final-self-test-output-0.5.0-r1"

    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "Portable ZIP was not found: $Archive"
    }
    if (Test-Path -LiteralPath $ExtractRoot) {
        throw "Refusing to overwrite the final extraction directory: $ExtractRoot"
    }
    if (Test-Path -LiteralPath $SelfTestRoot) {
        throw "Refusing to overwrite the final self-test directory: $SelfTestRoot"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $EntryNames = @($Zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    } finally {
        $Zip.Dispose()
    }

    if ($EntryNames.Count -eq 0) {
        throw "Portable ZIP is empty."
    }
    foreach ($EntryName in $EntryNames) {
        if (-not $EntryName.StartsWith("TrafficCrashNotebook/", [StringComparison]::Ordinal)) {
            throw "Unexpected ZIP root entry: $EntryName"
        }
        if ($EntryName -match '(^|/)\.\.(/|$)') {
            throw "Unsafe parent traversal entry in ZIP: $EntryName"
        }
    }

    New-Item -ItemType Directory -Path $ExtractRoot | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot

    $ApplicationFolder = Join-Path $ExtractRoot "TrafficCrashNotebook"
    $RequiredFiles = @(
        "TrafficCrashNotebook.exe",
        "START_HERE.txt",
        "BUILD_INFO.txt",
        "VERIFY_PORTABLE.bat",
        "VERIFY_PORTABLE.ps1",
        "PYSPELLCHECKER_LICENSE.txt",
        "_internal\spellchecker\resources\en.json.gz"
    )
    foreach ($RequiredFile in $RequiredFiles) {
        $RequiredPath = Join-Path $ApplicationFolder $RequiredFile
        if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
            throw "Required portable file is missing: $RequiredFile"
        }
    }

    $Executable = Join-Path $ApplicationFolder "TrafficCrashNotebook.exe"
    $Process = Start-Process -FilePath $Executable `
        -WorkingDirectory $ApplicationFolder `
        -ArgumentList "--self-test", "`"$SelfTestRoot`"" `
        -WindowStyle Hidden `
        -Wait -PassThru
    $SelfTestLog = Join-Path $SelfTestRoot "portable_self_test.txt"
    if ($Process.ExitCode -ne 0) {
        if (Test-Path -LiteralPath $SelfTestLog) {
            Get-Content -LiteralPath $SelfTestLog | Write-Host
        }
        throw "Extracted portable executable self-test failed with exit code $($Process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $SelfTestLog -PathType Leaf)) {
        throw "Extracted portable executable did not create a self-test log."
    }
    if (-not (Select-String -LiteralPath $SelfTestLog -Pattern '^PASS$' -Quiet)) {
        throw "Extracted portable executable self-test did not report PASS."
    }
    if (-not (Select-String -LiteralPath $SelfTestLog -Pattern '^Offline spell-check dictionary: PASS$' -Quiet)) {
        throw "Extracted portable executable did not pass the spell-check dictionary test."
    }
    foreach ($SelfTestPdf in @(
        "portable_self_test.pdf",
        "portable_self_test_compact_packet.pdf",
        "portable_self_test_quick_review.pdf",
        "portable_self_test_exchange_report.pdf"
    )) {
        $SelfTestPdfPath = Join-Path $SelfTestRoot $SelfTestPdf
        if (-not (Test-Path -LiteralPath $SelfTestPdfPath -PathType Leaf)) {
            throw "Extracted portable executable did not create: $SelfTestPdf"
        }
    }

    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if (Test-Path -LiteralPath $ChecksumFile -PathType Leaf) {
        $RecordedHash = ((Get-Content -LiteralPath $ChecksumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
        if ($RecordedHash -ne $Hash) {
            throw "Recorded checksum does not match the portable ZIP."
        }
    }

    Write-Host "Final extracted executable self-test: PASS"
    Get-Content -LiteralPath $SelfTestLog | Write-Host
    Write-Host "ZIP entries: $($EntryNames.Count)"
    Write-Host "Required portable files: PASS"
    Write-Host "SHA-256: $Hash"
} catch {
    Write-Error $_
    exit 1
}

exit 0
