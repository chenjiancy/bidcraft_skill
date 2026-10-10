# doc2docx converter channel (M5 prerequisite #2, 2026-10-10)
#
# Legacy .doc tender files cannot be parsed by python-docx; proj-gen /
# proj-contract require a .docx source. This tool uses local Word COM to
# save .doc as .docx (wdFormatXMLDocument=12).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/tools/doc2docx.ps1 `
#       -Src "E:\...\source_xxx.doc" [-Dst "E:\...\tender_xxx.docx"]
#
# Notes: Windows + Microsoft Word required; source .doc is opened read-only
# and never modified.
param(
    [Parameter(Mandatory = $true)][string]$Src,
    [string]$Dst = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Src -PathType Leaf)) {
    Write-Error "Source file not found: $Src"
    exit 1
}
if ($Dst -eq "") {
    $Dst = [System.IO.Path]::ChangeExtension($Src, ".docx")
}
if ([System.IO.Path]::GetExtension($Dst) -ne ".docx") {
    Write-Error "Target must be .docx: $Dst"
    exit 1
}
if (Test-Path -LiteralPath $Dst -PathType Leaf) {
    Write-Error "Target already exists, choose another path or remove it first: $Dst"
    exit 1
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
    $doc = $word.Documents.Open($Src, $false, $true, $false)
    $doc.SaveAs2($Dst, 12)   # wdFormatXMLDocument = 12
    $doc.Close($false)
    $doc = $null
    $word.Quit()
    $word = $null
    Write-Output "Converted: $Dst"
} catch {
    Write-Error ("Conversion failed: {0}" -f $_.Exception.Message)
    exit 1
} finally {
    if ($null -ne $doc) { try { $doc.Close($false) } catch {} }
    if ($null -ne $word) { try { $word.Quit() } catch {} }
}
