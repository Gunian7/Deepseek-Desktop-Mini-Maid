$ErrorActionPreference = "Continue"
$env:LISTENAI_HOME = 'F:\Output\Tools\listenai'
Set-Location 'F:\Output\LS26-ArcsMini3\arcs_mini'
.\arcs-sdk\env.ps1 | Out-Null
Write-Host "=== 开始编译 arcs_mini3 ==="
.\build.ps1 -S .\apps\arcs-mini -B build-arcs-mini3 -DBOARD=arcs_mini3 2>&1
Write-Host "=== BUILD EXIT=$LASTEXITCODE ==="
