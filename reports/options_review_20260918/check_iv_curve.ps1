$ErrorActionPreference = 'Stop'
$curveRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$curveCheckPath = Join-Path $curveRoot 'iv_curve_excel_check.xlsx'
Copy-Item -LiteralPath (Join-Path $curveRoot 'Galicia_options_analysis.xlsx') -Destination $curveCheckPath -Force
$curveData = Get-Content -LiteralPath (Join-Path $curveRoot 'analysis.json') -Raw | ConvertFrom-Json
$curveExcel = $null
$curveBook = $null
try {
    $curveExcel = New-Object -ComObject Excel.Application
    $curveExcel.Visible = $false
    $curveExcel.DisplayAlerts = $false
    $curveExcel.AutomationSecurity = 3
    $curveBook = $curveExcel.Workbooks.Open($curveCheckPath, 0, $false)
    $curveSheet = $curveBook.Worksheets.Item('IV curve explorer')
    $curveExcel.CalculateFull()
    foreach ($curveTest in @(@('call','2026-09-01',1,'2026-09-02'), @('call','2026-09-16',-1,'2026-09-15'), @('put','2026-08-21',18,'2026-09-16'))) {
        $curveSheet.Range('B6').Value2 = $curveTest[0]
        $curveSheet.Range('B7').Value2 = ([datetime]::ParseExact($curveTest[1], 'yyyy-MM-dd', $null)).ToOADate()
        $curveSheet.Range('B8').Value2 = [double]$curveTest[2]
        $curveExcel.CalculateFull()
        $curveExpectedDate = ([datetime]::ParseExact($curveTest[3], 'yyyy-MM-dd', $null)).ToOADate()
        if ($curveSheet.Range('B9').Value2 -ne $curveExpectedDate) { throw 'Comparison date did not update.' }
        $curveExpected = $curveData.rows | Where-Object { $_.date -eq $curveTest[3] -and $_.side -eq $curveTest[0] -and $_.k -eq 6800 }
        if ([Math]::Abs($curveSheet.Range('C52').Value2 - $curveExpected.iv) -gt 0.00000001) { throw 'Comparison curve IV did not update.' }
    }
    $curveSheet.Range('B8').Value2 = -1
    $curveExcel.CalculateFull()
    if ($curveSheet.Range('D6').Value2 -eq 'Ready' -or $curveSheet.Range('B9').Value2 -ne '') { throw 'Outside-history step was accepted.' }
    $curveSheet.Range('B6').Value2 = 'call'
    $curveSheet.Range('B7').Value2 = ([datetime]'2026-09-01').ToOADate()
    $curveSheet.Range('B8').Value2 = 1
    $curveSheet.Range('B10').Value2 = 7000
    $curveExcel.CalculateFull()
    $curveExpected = $curveData.rows | Where-Object { $_.date -eq '2026-09-16' -and $_.side -eq 'call' -and $_.k -eq 7000 }
    if ([Math]::Abs($curveSheet.Range('J57').Value2 - $curveExpected.iv) -gt 0.00000001) { throw 'Watched strike did not update.' }
    if ($curveSheet.ChartObjects().Count -ne 2) { throw 'Expected two charts.' }
    $curveChart = $curveSheet.ChartObjects(1).Chart
    $curveX = $curveChart.SeriesCollection(1).XValues
    if ($curveX.GetValue($curveX.GetLowerBound(0)) -ne 4200 -or $curveX.GetValue($curveX.GetUpperBound(0)) -ne 9900) { throw 'Curve strikes are not numeric X coordinates.' }
    if ($curveSheet.Range('B7').Validation.Type -ne 3) { throw 'Date dropdown absent.' }
    Write-Output ('Excel checks passed: forward/back steps, call/put switching, watched strike, date dropdown and numeric strike axis. Chart type: ' + $curveChart.ChartType)
    $curveBook.Close($false)
    $curveBook = $null
} finally {
    if ($null -ne $curveBook) { $curveBook.Close($false) }
    if ($null -ne $curveExcel) { $curveExcel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($curveExcel) }
}
