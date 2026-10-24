$ErrorActionPreference = "Continue"
$env:PATH = "F:\Output\Tools\platform-tools;" + $env:PATH
Set-Location 'F:\Output\LS26-ArcsMini3\arcs_mini'

$D = "6d7b101a1f1dcba5"
Write-Host "=== 只烧 emoji 分区 0x380000（不动 tone/app）==="
adb -s $D shell recovery
Start-Sleep -Seconds 4

$boot = $null
for ($i = 0; $i -lt 25; $i++) {
    $line = adb devices | Select-String "BOOT-"
    if ($line) { $boot = ($line -split "\s+")[0]; break }
    Start-Sleep -Seconds 1
}
if (-not $boot) { Write-Host "FAIL: 没等到 BOOT 设备"; exit 1 }
Write-Host "BOOT device: $boot"

adb -s $boot push res\arcs-mini\emoji.bin /RAW/NAND/380000
Write-Host "=== 烧完，重启 ==="
adb -s $boot reboot
Start-Sleep -Seconds 2
adb -s $D wait-for-device
adb devices -l
