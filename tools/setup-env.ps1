$ErrorActionPreference = "Continue"
$env:LISTENAI_HOME = 'F:\Output\Tools\listenai'
Set-Location 'F:\Output\LS26-ArcsMini3\arcs_mini'
Write-Host "=== 开始安装工具链，LISTENAI_HOME=$env:LISTENAI_HOME ==="
.\arcs-sdk\env.ps1
Write-Host "=== ENV SCRIPT DONE ==="
Write-Host "ARCS_BASE=$env:ARCS_BASE"
Write-Host "NUCLEI_TOOLCHAIN_PATH=$env:NUCLEI_TOOLCHAIN_PATH"
Write-Host "LISTENAI_TOOLS_PATH=$env:LISTENAI_TOOLS_PATH"
