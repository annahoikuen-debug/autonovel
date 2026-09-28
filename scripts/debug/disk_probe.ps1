$ErrorActionPreference = "Continue"
Write-Host "=== Volumes ===" -ForegroundColor Cyan
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    $sizeGB = [math]::Round($_.Size / 1GB, 1)
    $freeGB = [math]::Round($_.FreeSpace / 1GB, 1)
    Write-Host ("  {0}  label='{1}'  size={2}GB free={3}GB" -f $_.DeviceID, $_.VolumeName, $sizeGB, $freeGB)
}
Write-Host ""
Write-Host "=== Physical disks ===" -ForegroundColor Cyan
Get-PhysicalDisk -ErrorAction SilentlyContinue |
    Select-Object DeviceId, FriendlyName, MediaType, BusType, @{Name = "SizeGB"; Expression = { [math]::Round($_.Size / 1GB, 1) } } |
    Format-Table -AutoSize | Out-String -Width 140

Write-Host ""
Write-Host "=== pycache coverage in src/ ===" -ForegroundColor Cyan
$py = Get-ChildItem -Path "src" -Recurse -File -Filter "*.py"
$pycacheDirs = Get-ChildItem -Path "src" -Recurse -Directory -Filter "__pycache__"
Write-Host ("  .py files      : {0}" -f $py.Count)
Write-Host ("  __pycache__ dirs: {0}" -f $pycacheDirs.Count)
$pyc = Get-ChildItem -Path "src" -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue
Write-Host ("  .pyc files     : {0}" -f $pyc.Count)

Write-Host ""
Write-Host "=== node_modules size ===" -ForegroundColor Cyan
if (Test-Path "frontend\node_modules") {
    $sz = (Get-ChildItem "frontend\node_modules" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    Write-Host ("  frontend\node_modules = {0} MB" -f [math]::Round($sz / 1MB, 1))
}
