$os = Get-CimInstance Win32_OperatingSystem
$totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
Write-Host "TotalRAM_GB = $totalGB"
Write-Host "FreeRAM_GB  = $freeGB"
Write-Host ""
Write-Host "--- Top memory processes ---"
Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 12 Name, Id, @{Name = 'MemMB'; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } } | Format-Table -AutoSize | Out-String -Width 200
Write-Host "--- python processes ---"
Get-Process python* -ErrorAction SilentlyContinue | Select-Object Name, Id, @{Name = 'MemMB'; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } }, StartTime | Format-Table -AutoSize | Out-String -Width 200
Write-Host "--- page file ---"
$cs = Get-CimInstance Win32_ComputerSystem
Write-Host ("AutomaticManagedPagefile = " + $cs.AutomaticManagedPagefile)
Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage | Format-Table -AutoSize | Out-String -Width 200
