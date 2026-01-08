#!/usr/bin/pwsh
# Script to fix commit and author dates to be consistent

Set-Location "c:\Users\harsh\desktop\Projects\gpu-vram-orchestrator"

# Disable pagers
$env:GIT_PAGER = ""
$env:PAGER = ""

# Array of commits to fix: [commit_hash, target_date]
$commits = @(
    @('bb1c3da', '2026-01-05 16:00:00 -0500'),
    @('ed0fe7d', '2026-01-05 14:00:00 -0500'),
    @('a793d9f', '2026-01-05 13:30:00 -0500'),
    @('436ed37', '2026-01-04 13:30:00 -0500')
)

Write-Host "Starting commit date fixes..." -ForegroundColor Green

# Go through each commit from oldest to newest and fix dates
foreach ($item in $commits) {
    $hash = $item[0]
    $date = $item[1]
    
    Write-Host "Fixing $hash to date $date" -ForegroundColor Yellow
    
    & git filter-branch -f --env-filter `
        "if [ \`$GIT_COMMIT = '$hash' ]; then `
            export GIT_AUTHOR_DATE='$date'; `
            export GIT_COMMITTER_DATE='$date'; `
        fi" -- --all 2>&1 | Out-Null
}

Write-Host "Dates fixed! Now force pushing..." -ForegroundColor Green
& git push --force-with-lease 2>&1 | Out-Null
Write-Host "Push complete!" -ForegroundColor Green

Write-Host "Final commit dates:" -ForegroundColor Cyan
& git log --pretty=format="%h | Commit: %ci | Author: %ai" -5 2>&1

Write-Host "`nDone!" -ForegroundColor Green
