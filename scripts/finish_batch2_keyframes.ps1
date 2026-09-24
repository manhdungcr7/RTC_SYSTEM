param([Parameter(Mandatory = $true)][int]$DownloadPid)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$report = Join-Path $repo 'artifacts/batch2_keyframes_verified.json'
$log = Join-Path $repo 'artifacts/batch2_keyframe_finish.log'

function Write-Status([string]$message) {
    "$(Get-Date -Format o) $message" | Add-Content -LiteralPath $log
}

try {
    if (Get-Process -Id $DownloadPid -ErrorAction SilentlyContinue) {
        Write-Status "WAITING pid=$DownloadPid"
        Wait-Process -Id $DownloadPid
    }
    if (-not (Test-Path -LiteralPath $report)) {
        Write-Status 'DOWNLOAD_OR_VERIFICATION_FAILED: report missing; backend unchanged'
        exit 1
    }

    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if ($result.keyframes -le 0 -or $result.maps -le 0) {
        throw 'Verification report has no keyframes or maps'
    }
    Write-Status "VERIFIED keyframes=$($result.keyframes) maps=$($result.maps) videos=$($result.videos)"

    & docker restart aic-backend | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restart backend' }
    Write-Status 'BACKEND_RESTARTED'

    for ($attempt = 1; $attempt -le 120; $attempt++) {
        try {
            $health = Invoke-RestMethod 'http://localhost:8080/health' -TimeoutSec 5
            if ($health.faiss.branches.metaclip2 -eq 635181) {
                $response = Invoke-WebRequest 'http://localhost:8080/media/frame/M01_V001/1' -MaximumRedirection 0 -SkipHttpErrorCheck -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    Write-Status 'READY: backend serves M01_V001 keyframe from local data'
                    exit 0
                }
            }
        } catch { }
        Start-Sleep -Seconds 5
    }
    throw 'Backend did not serve a local Batch 2 keyframe within 10 minutes'
} catch {
    Write-Status "ERROR: $($_.Exception.Message)"
    exit 1
}
