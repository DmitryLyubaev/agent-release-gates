$ErrorActionPreference = 'Stop'
uv run python scripts/offline_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Offline pipeline failed' }
$demoResult = Get-Content -LiteralPath 'artifacts/offline-demo.json' -Raw | ConvertFrom-Json
foreach ($demoCase in @(@('pass', 0), @('exact_reject', 1), @('semantic_reject', 1), @('incomplete', 2))) {
    $decisionId = $demoResult.decisions.($demoCase[0]).id
    uv run release-gates report --decision-id $decisionId > $null
    if ($LASTEXITCODE -ne $demoCase[1]) { throw "Unexpected CLI exit for $($demoCase[0])" }
    Write-Output "$($demoCase[0]): exit $LASTEXITCODE"
}
