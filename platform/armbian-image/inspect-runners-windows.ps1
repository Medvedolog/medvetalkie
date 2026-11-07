# Read-only Windows-side diagnostic for MedveTalkie self-hosted runners.
# Do not print or send GitHub tokens/runner credentials.
$ErrorActionPreference = 'Continue'
Write-Output '=== Windows machine and memory ==='
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture, @{N='RAM_GiB';E={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}}
Write-Output '=== Local Windows GitHub Actions runner services ==='
$services = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -like 'actions.runner.*' })
if ($services.Count -eq 0) {
    Write-Output 'No native Windows runner service found; it may run inside WSL2.'
} else {
    $services | Select-Object Name, State, StartMode
}
Write-Output '=== WSL distributions ==='
if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    wsl.exe --list --verbose
} else {
    Write-Output 'WSL executable not found.'
}
Write-Output '=== Available Windows disk capacity ==='
Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='Free_GiB';E={[math]::Round($_.Free/1GB,1)}}, Root
Write-Output '=== GitHub repo self-hosted runners (gh CLI; requires repo admin token) ==='
if (Get-Command gh -ErrorAction SilentlyContinue) {
    foreach ($repo in @('medvetalkie','medvewrt','opiz3-wlan-backport')) {
        Write-Output "Repo: Medvedolog/$repo"
        gh api "repos/Medvedolog/$repo/actions/runners?per_page=100" --jq '.runners[] | [.name, .os, .status, (.busy|tostring), ([.labels[].name]|join(","))] | @tsv'
        if ($LASTEXITCODE -ne 0) {
            Write-Output "Runner API unavailable or not authorized for $repo."
        }
    }
} else {
    Write-Output 'gh CLI is not installed; inspect GitHub repo Settings > Actions > Runners.'
}
Write-Output '=== What MedveTalkie needs ==='
Write-Output 'Repo-scoped runner for Medvedolog/medvetalkie, running Linux/X64 inside WSL2, custom label armbian-image, >=8 GiB RAM, >=50 GiB actual free disk, Docker and sudo.'
Write-Output 'Use Bash inside WSL2: bash platform/armbian-image/home-runner-preflight.sh "$HOME"'
