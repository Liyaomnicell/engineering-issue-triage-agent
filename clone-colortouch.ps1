$ErrorActionPreference = 'Stop'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$repositories = @(
 'beaconservice', 'cabinetrenametool', 'common-telemetrylibrary',
 'common-telemetryservice', 'ct-angular-amr', 'ct-app-corelibrary',
 'ct-colortouch', 'ct-colortouch-test', 'ct-core-libraries',
 'ct-ctserviceinstall', 'ct-databases', 'ct-installers',
 'ct-library-messageforwarding', 'ct-service-deviceservice',
 'ct-service-hardwareservice', 'ct-service-printingservice',
 'ct-testautomation', 'ct-testautomation-ctupgradewizard',
 'ct-testautomation-utilities', 'hal-cabinet', 'medassignment',
 'omniautomationagent', 'rrt-xtsetupwizard',
 'tool-cabinet-phi-data-de-identification', 'tool-cabinettester'
)
$destination = Join-Path $PSScriptRoot 'source-colortouch'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$results = foreach ($repository in $repositories) {
 $url = "https://bitbucket.org/omnicell/$repository.git"
 $path = Join-Path $destination $repository
 if (Test-Path -LiteralPath $path) {
  Write-Output "SKIP existing directory: $repository" | Out-Host
  $status = 'existing-directory'
 } else {
  Write-Output "Cloning $repository" | Out-Host
  & git -c credential.interactive=never clone --config core.longpaths=true -- $url $path
  $status = if ($LASTEXITCODE -eq 0) { 'cloned' } else { 'failed' }
 }
 $commit = $null
 $branch = $null
 if (Test-Path -LiteralPath (Join-Path $path '.git')) {
  $commit = & git -C $path rev-parse HEAD
  $branch = & git -C $path branch --show-current
 }
 [PSCustomObject]@{Repository=$repository;Url=$url;Path=$path;Status=$status;Branch=$branch;Commit=$commit}
}
$results | Export-Csv -LiteralPath (Join-Path $destination 'repositories.csv') -NoTypeInformation -Encoding UTF8
$results | Select-Object Repository,Status,Branch | Format-Table
if (@($results | Where-Object Status -eq 'failed').Count) { exit 1 }
