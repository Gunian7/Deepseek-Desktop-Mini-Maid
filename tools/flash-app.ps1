$ErrorActionPreference = "Continue"
$env:PATH = "F:\Output\Tools\platform-tools;" + $env:PATH
$env:LISTENAI_HOME = 'F:\Output\Tools\listenai'
Set-Location 'F:\Output\LS26-ArcsMini3\arcs_mini'

Write-Host "=== 烧录前设备 ==="
adb devices -l

Write-Host "=== 开始烧录 app 分区 ==="
.\adb_download.ps1 -S res\arcs-mini3 -B build-arcs-mini3 app 2>&1
Write-Host "=== FLASH EXIT=$LASTEXITCODE ==="
