param(
    [int]$ExpectedRows = 635181
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$faiss = [IO.Path]::GetFullPath((Join-Path $repo 'docker/volumes/faiss'))
$live = [IO.Path]::GetFullPath((Join-Path $faiss 'metaclip2'))
$stage = [IO.Path]::GetFullPath((Join-Path $repo 'artifacts/batch2_metaclip2/merged_index'))
$backup = [IO.Path]::GetFullPath((Join-Path $faiss ('metaclip2_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))))
$failed = [IO.Path]::GetFullPath((Join-Path $faiss ('metaclip2_failed_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))))
$compose = Join-Path $repo 'docker/docker-compose.yml'

foreach ($path in @($faiss, $live, $stage, $backup, $failed)) {
    if (-not $path.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path outside workspace: $path"
    }
}
if (-not (Test-Path -LiteralPath $live -PathType Container)) { throw "Missing live index: $live" }
if (-not (Test-Path -LiteralPath $stage -PathType Container)) { throw "Missing staged index: $stage" }
foreach ($file in @('index.faiss', 'meta.parquet')) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $file) -PathType Leaf)) {
        throw "Missing staged file: $file"
    }
}
if ((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $failed)) {
    throw 'Backup/failed target already exists'
}

docker compose -f $compose stop backend
if ($LASTEXITCODE -ne 0) { throw 'Could not stop backend; live index unchanged' }

$swapped = $false
try {
    Rename-Item -LiteralPath $live -NewName (Split-Path $backup -Leaf)
    try {
        Move-Item -LiteralPath $stage -Destination $live
        $swapped = $true
    } catch {
        Rename-Item -LiteralPath $backup -NewName 'metaclip2'
        throw
    }

    docker compose -f $compose up -d --no-deps backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend did not start' }
    $deadline = (Get-Date).AddMinutes(5)
    do {
        Start-Sleep -Seconds 5
        try {
            $health = Invoke-RestMethod -Uri 'http://localhost:8080/health' -TimeoutSec 10
            if ($health.faiss.branches.metaclip2 -eq $ExpectedRows) {
                Write-Output "ACTIVE rows=$ExpectedRows backup=$backup"
                exit 0
            }
        } catch { }
    } while ((Get-Date) -lt $deadline)
    throw "Backend health did not report $ExpectedRows MetaCLIP rows"
} catch {
    $reason = $_
    if ($swapped) {
        docker compose -f $compose stop backend | Out-Null
        Rename-Item -LiteralPath $live -NewName (Split-Path $failed -Leaf)
        Rename-Item -LiteralPath $backup -NewName 'metaclip2'
    }
    docker compose -f $compose up -d --no-deps backend | Out-Null
    throw "Activation failed and old index was restored: $reason"
}
