# 单文件页数查询（Word COM）：输出页数整数到 stdout。
# 用法：powershell -File verify_pages_one.ps1 -File "path.docx"
param(
    [Parameter(Mandatory=$true)][string]$File
)
$ErrorActionPreference = "Stop"
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($File, $false, $true)
    try {
        [int]$doc.ComputeStatistics(2)   # wdStatisticPages = 2
    } finally {
        $doc.Close($false)
    }
} finally {
    if ($word) { $word.Quit() }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
