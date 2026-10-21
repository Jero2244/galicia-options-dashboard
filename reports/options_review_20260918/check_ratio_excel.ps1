$ErrorActionPreference = 'Stop'
$ratioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ratioTestPath = Join-Path $ratioRoot 'ratio_excel_check.xlsx'
Copy-Item -LiteralPath (Join-Path $ratioRoot 'Galicia_options_analysis.xlsx') -Destination $ratioTestPath -Force
$ratioExcel = $null
$ratioBook = $null
try {
    $ratioExcel = New-Object -ComObject Excel.Application
    $ratioExcel.Visible = $false
    $ratioExcel.DisplayAlerts = $false
    $ratioExcel.AutomationSecurity = 3
    $ratioBook = $ratioExcel.Workbooks.Open($ratioTestPath, 0, $false)
    $ratioSheet = $ratioBook.Worksheets.Item('Ratio explorer')
    $ratioExcel.CalculateFull()
    if ([Math]::Abs($ratioSheet.Range('D56').Value2 - (-202.87)) -gt 0.00001) { throw 'Excel initial 1:2 cost did not match.' }
    if ($ratioSheet.Range('B7').Validation.Type -ne 3) { throw 'Strike dropdown is absent.' }
    $ratioSheet.Range('B9').Value2 = '1:1'
    $ratioExcel.CalculateFull()
    if ([Math]::Abs($ratioSheet.Range('D56').Value2 - 86.78) -gt 0.00001) { throw 'Excel 1:1 cost did not update.' }
    $ratioSheet.Range('B6').Value2 = 'put'
    $ratioSheet.Range('B7').Value2 = 7000
    $ratioSheet.Range('B8').Value2 = 6600
    $ratioSheet.Range('B9').Value2 = '1:2'
    $ratioExcel.CalculateFull()
    if ([Math]::Abs($ratioSheet.Range('D56').Value2 - (-17.87)) -gt 0.00001) { throw 'Excel put spread did not update.' }
    $ratioSheet.Range('B7').Value2 = 9900
    $ratioExcel.CalculateFull()
    if ($ratioSheet.Range('D6').Value2 -eq 'Ready' -or $ratioSheet.Range('D56').Value2 -ne '') { throw 'Unavailable put strike was accepted.' }
    $ratioSheet.Range('B6').Value2 = 'call'
    $ratioSheet.Range('B7').Value2 = 6800
    $ratioSheet.Range('B8').Value2 = 7000
    $ratioSheet.Range('B9').Value2 = '1:2'
    $ratioExcel.CalculateFull()
    if ($ratioSheet.ChartObjects().Count -ne 2) { throw 'Expected two charts.' }
    $ratioChart = $ratioSheet.ChartObjects(1).Chart
    $ratioValues = $ratioChart.SeriesCollection(1).Values
    if ([Math]::Abs($ratioValues.GetValue($ratioValues.GetUpperBound(0)) - (-202.87)) -gt 0.00001) { throw 'Chart did not follow the controls.' }
    Write-Output ('Native Excel checks passed. Dropdown: ' + $ratioSheet.Range('B7').Validation.Formula1)
    Write-Output ('Latest cost: ' + $ratioSheet.Range('D56').Value2 + '. Long IV: ' + $ratioSheet.Range('F56').Value2 + '. Short IV: ' + $ratioSheet.Range('G56').Value2)
    $ratioBook.Close($false)
    $ratioBook = $null
} finally {
    if ($null -ne $ratioBook) { $ratioBook.Close($false) }
    if ($null -ne $ratioExcel) { $ratioExcel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($ratioExcel) }
}
