param(
    [string]$ApplicationFolder = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

try {
$ErrorActionPreference = "Stop"
$Executable = Join-Path $ApplicationFolder "TrafficCrashNotebook.exe"
if (-not (Test-Path $Executable)) {
    throw "TrafficCrashNotebook.exe was not found in $ApplicationFolder"
}

$VerificationDirectory = Join-Path $env:TEMP "TrafficCrashNotebook-Portable-Verification"
if (Test-Path $VerificationDirectory) {
    Remove-Item $VerificationDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $VerificationDirectory -Force | Out-Null

$Process = Start-Process -FilePath $Executable -ArgumentList "--self-test", "`"$VerificationDirectory`"" -Wait -PassThru
$Log = Join-Path $VerificationDirectory "portable_self_test.txt"
if ($Process.ExitCode -ne 0 -or -not (Test-Path $Log)) {
    throw "Portable verification failed. Exit code: $($Process.ExitCode)"
}
Get-Content $Log
if (-not (Select-String -Path $Log -Pattern "^PASS$" -Quiet)) {
    throw "Portable verification did not report PASS."
}
Write-Host ""
Write-Host "Traffic Crash Notebook portable verification: PASS" -ForegroundColor Green
Write-Host "Verification files: $VerificationDirectory"
} catch {
    Write-Error $_
    exit 1
}
exit 0
