param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

try {
    if ($Tag -notmatch '^v\d+\.\d+\.\d+$') {
        throw "Release tag must use vMAJOR.MINOR.PATCH format: $Tag"
    }
    $Version = $Tag.Substring(1)
    $VersionFile = Join-Path $ProjectRoot "src\traffic_crash_notebook\__init__.py"
    $VersionMatch = Select-String -LiteralPath $VersionFile -Pattern '^__version__\s*=\s*"([^"]+)"$'
    if (-not $VersionMatch -or $VersionMatch.Matches[0].Groups[1].Value -ne $Version) {
        throw "Git tag $Tag does not match the application version in $VersionFile."
    }

    $ReleaseDirectory = Join-Path $ProjectRoot "release"
    $Archive = Join-Path $ReleaseDirectory "TrafficCrashNotebook-$Version-Windows-Portable.zip"
    $Checksum = "$Archive.sha256.txt"
    $UpdateManifest = Join-Path $ReleaseDirectory "update-manifest.json"
    $FilesManifest = Join-Path $ReleaseDirectory "TrafficCrashNotebook-$Version-Windows-Portable.files.json"
    $ReleaseNotes = Join-Path $ProjectRoot "docs\RELEASE_NOTES.md"
    $Assets = @($Archive, $Checksum, $UpdateManifest, $FilesManifest)
    foreach ($Asset in $Assets) {
        if (-not (Test-Path -LiteralPath $Asset -PathType Leaf)) {
            throw "Required release asset was not created: $Asset"
        }
        if ((Get-Item -LiteralPath $Asset).Length -le 0) {
            throw "Required release asset is empty: $Asset"
        }
    }

    $Manifest = Get-Content -LiteralPath $UpdateManifest -Raw | ConvertFrom-Json
    if ($Manifest.version -ne $Version -or $Manifest.release_tag -ne $Tag) {
        throw "The generated update manifest does not match $Tag."
    }
    if ($Manifest.windows_portable.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "The generated update manifest does not contain a valid package hash."
    }
    $ArchiveHash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $FilesManifestHash = (Get-FileHash -LiteralPath $FilesManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Manifest.windows_portable.sha256 -ne $ArchiveHash) {
        throw "The update manifest hash does not match the portable ZIP."
    }
    if ($Manifest.package_manifest.sha256 -ne $FilesManifestHash) {
        throw "The update manifest hash does not match the complete file manifest."
    }
    $ChecksumText = (Get-Content -LiteralPath $Checksum -Raw).Trim().ToLowerInvariant()
    if (-not $ChecksumText.StartsWith($ArchiveHash)) {
        throw "The checksum file does not match the portable ZIP."
    }

    & gh release create $Tag @Assets `
        --verify-tag `
        --title "Traffic Crash Notebook $Version" `
        --notes-file $ReleaseNotes
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub release creation failed with exit code $LASTEXITCODE."
    }
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
