# 页数校验（V5）：格式配置「独占一面·文件级」→ 项目模板对应文件必须 1 页（严禁跨页）
# 用法：powershell -File verify_pages.ps1 -FormatConfigJson "scripts\m5_project\format_config.json"
#                                    -ProjDir "项目级\<项目>\项目模板" -OutJson out.json
# 规则（用户 2026-10-10 V5 设计，企业模板废弃）：
#   - format_config.json「独占一面·文件级」中**无括号说明**的项（纯文件名）
#     = 该文件必须独占 1 页（封面/密封袋封面/开标一览表/投标函附录/法代/授权/
#       中小企业声明函/承诺书）→ 项目模板严禁跨页，必须 1 页；
#   - 带括号说明的项（如 投标函.docx（（一）投标函正文独占一面））= 内容级独占，
#     不在本脚本强制整个文件 1 页（由 agent 检查兜底）；
#   - 内容级独占（附表1/附表3/附表8）由 page_fit 收敛 + agent 检查，本脚本不校验。
param(
    [Parameter(Mandatory=$true)][string]$FormatConfigJson,
    [Parameter(Mandatory=$true)][string]$ProjDir,
    [Parameter(Mandatory=$true)][string]$OutJson
)
$ErrorActionPreference = "Stop"
$cfg = Get-Content -LiteralPath $FormatConfigJson -Encoding UTF8 -Raw | ConvertFrom-Json
$ownFiles = @()
foreach ($item in $cfg."独占一面"."文件级") {
    $s = [string]$item
    if ($s -notmatch "（") {           # 纯文件名 = 强制独占 1 页
        $ownFiles += $s
    }
}
$results = @()
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    function Get-PageCount($path) {
        $doc = $word.Documents.Open($path, $false, $true)   # ReadOnly
        try {
            return $doc.ComputeStatistics(2)                # wdStatisticPages = 2
        } finally {
            $doc.Close($false)
        }
    }
    foreach ($projFile in Get-ChildItem -LiteralPath $ProjDir -Filter "*.docx") {
        if ($projFile.Name -notin $ownFiles) {
            $results += [pscustomobject]@{
                文件 = $projFile.Name
                独占一面要求 = $false
                项目模板页数 = 0
                结论 = "跳过"
                说明 = "非文件级独占（格式配置未要求整文件独占 1 页）"
            }
            continue
        }
        $projPages = Get-PageCount $projFile.FullName
        $ok = ($projPages -eq 1)
        $results += [pscustomobject]@{
            文件 = $projFile.Name
            独占一面要求 = $true
            项目模板页数 = $projPages
            结论 = $(if ($ok) { "通过" } else { "不通过" })
            说明 = $(if ($ok) { "" } else { "格式配置要求独占一面，项目模板跨页（严禁跨页）" })
        }
    }
} finally {
    if ($word) { $word.Quit() }
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
$results | ConvertTo-Json -Depth 3 | Out-String | ForEach-Object {
    [System.IO.File]::WriteAllText($OutJson, $_, (New-Object System.Text.UTF8Encoding($false)))
}
