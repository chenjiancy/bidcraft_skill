# 标书匠 · 生产环境升级脚本（唯一升级通道：从 GitHub main 拉取）
# 本目录永不本地开发；升级只做 fast-forward，本地任何未提交改动都会中止升级。
# 认证模式：
#   手动运行        -> 使用 origin（SSH，需本机用户账户的 GitHub 凭据）
#   CI/CD 自动部署   -> 设置环境变量 GITHUB_TOKEN，走 HTTPS + token 认证（runner 服务账户可用）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# git 路径修复：runner 服务账户(NETWORK SERVICE)继承系统 PATH，不含用户 PATH 的 D:\Git；
# 若 git 不在 PATH，主动注入本机 git 安装路径（手动运行不受影响，幂等）
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $candidates = @('D:\Git\cmd', 'C:\Program Files\Git\cmd', 'C:\Program Files\Git\bin')
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c 'git.exe')) {
            $env:Path = "$c;" + $env:Path
            Write-Host "git 不在 PATH，已注入: $c" -ForegroundColor Yellow
            break
        }
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "未找到 git 可执行文件（已尝试 D:\Git\cmd、C:\Program Files\Git\cmd、C:\Program Files\Git\bin）"
    }
}

# git 安全信任本生产目录：目录属 Administrators，runner 服务账户(NETWORK SERVICE)运行 git 会
# 触发 dubious ownership 拒绝；此命令对其账户幂等生效（重复添加无害）
git config --global --add safe.directory 'E:/标书匠生产' 2>$null

# 认证模式：
#   手动运行        -> 使用 origin（SSH，需本机用户账户的 GitHub 凭据）
#   CI/CD 自动部署   -> SSH + 专用 deploy key（本机 github.com:443 被网络限制，
#                       HTTPS+token 拉取不通；改用 ssh 22 端口 + 只读 deploy key，
#                      key 已通过 GitHub API 注册，私钥在本目录 .deploy/bidcraft_deploy）
$GitArgs = @()
if ($env:GITHUB_TOKEN) {
    $env:GIT_SSH_COMMAND = "ssh -i E:/标书匠生产/.deploy/bidcraft_deploy -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=E:/标书匠生产/.deploy/known_hosts"
    $GitArgs = @()
    # 22 端口传输在国内网络常被干扰（连接建立但数据挂起）；GitHub 官方提供 SSH over 443，
    # 443 为标准 HTTP 端口更稳定，deploy key 同样适用于 ssh.github.com
    $RepoUrl = "ssh://git@ssh.github.com:443/chenjiancy/bidcraft_skill.git"
    Write-Host "认证模式：SSH + 专用 deploy key（CI/CD 自动部署；443 受限改走 22）" -ForegroundColor Yellow
} else {
    $RepoUrl = $null
    Write-Host "认证模式：SSH origin（手动升级）" -ForegroundColor Yellow
}

# git 命令带重试（HTTPS 拉取偶发 TLS/schannel 抖动，重试 3 次）
function Invoke-GitRetry {
    param([string]$Label, [scriptblock]$Cmd)
    for ($i = 1; $i -le 4; $i++) {
        & $Cmd
        if ($LASTEXITCODE -eq 0) { return 0 }
        if ($i -lt 4) {
            Write-Host ("  {0} 失败(exit {1})，{2} 秒后重试 {3}/3..." -f $Label, $LASTEXITCODE, 3, $i) -ForegroundColor Yellow
            Start-Sleep -Seconds 3
        }
    }
    return $LASTEXITCODE
}

Write-Host "== 0) 防污染检查（本地已跟踪文件有改动则中止）==" -ForegroundColor Cyan
# 只检查已跟踪文件的改动；untracked 运维文件（版本记录.txt/生产环境说明.txt 等）不阻塞升级
$dirty = (git status --porcelain) | Where-Object { $_ -notmatch '^\?\?' }
if ($dirty) {
    Write-Host "[中止] 生产目录存在未提交改动，禁止覆盖升级：" -ForegroundColor Red
    $dirty
    Write-Host "请人工核查生产目录改动（生产目录不应有任何手动修改），确认后选择："
    Write-Host "  - 若误改，git checkout -- . 恢复后重跑本脚本"
    Write-Host "  - 若确需保留改动，先在开发仓库 E:\bidcraft_skill 完成并推送后重新部署"
    exit 1
}

Write-Host "== 1) 同步 GitHub main（tarball 快照；SSH pack 传输受网络干扰时降级）==" -ForegroundColor Cyan
# 背景：国内网络对 GitHub SSH 大数据（git fetch pack）有干扰——连接建立但数据挂起；
# git smart-HTTP 主域 github.com:443 也被网络阻断。实测 codeload.github.com:443 HTTPS
# 大文件下载稳定，故生产同步改为：API 取远端 SHA → codeload 下载 tarball → robocopy 同步工作区。
$RemoteSha = ""
try {
    if ($env:GITHUB_TOKEN) {
        $RemoteSha = (Invoke-RestMethod -Uri 'https://api.github.com/repos/chenjiancy/bidcraft_skill/commits/main' -Headers @{Authorization = "token $env:GITHUB_TOKEN"} -TimeoutSec 30).sha
    } else {
        $RemoteSha = (Invoke-RestMethod -Uri 'https://api.github.com/repos/chenjiancy/bidcraft_skill/commits/main' -TimeoutSec 30).sha
    }
} catch {
    Write-Host "[失败] 获取远端 main SHA 失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
# python 探测（zip 解压与冒烟共用）
$py = $null
foreach ($c in @("C:\Python312\python.exe", "C:\Python311\python.exe", "D:\anaconda3\python.exe")) {
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) { $py = "python" }
# 已同步判断：本地 HEAD 等于远端 SHA，或最近 prod-sync commit 已含该远端 SHA（包装 commit 场景）
$LocalSha = (git rev-parse HEAD).Trim()
$SyncMsg = (git log -1 --format="%s" --grep="prod-sync $RemoteSha" 2>$null).Trim()
if ($LocalSha -eq $RemoteSha -or $SyncMsg) {
    $behind = "0"
} else {
    $behind = "1"
    Write-Host ("远端 main = {0}，本地 = {1}，开始同步..." -f $RemoteSha.Substring(0,7), $LocalSha.Substring(0,7))
    $Snapshot = Join-Path $env:TEMP "bidcraft_main.zip"
    $ExtractDir = Join-Path $env:TEMP "bidcraft_sync"
    $synced = $false
    for ($try = 1; $try -le 3; $try++) {
        Write-Host ("  下载仓库快照（api zipball，第 {0}/3 次）..." -f $try)
        Remove-Item $Snapshot -Force -ErrorAction SilentlyContinue
        & curl.exe -L -s -o $Snapshot "https://api.github.com/repos/chenjiancy/bidcraft_skill/zipball/main"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Snapshot) -or (Get-Item $Snapshot).Length -lt 100000) {
            Write-Host "  下载失败或文件过小，重试" -ForegroundColor Yellow
            continue
        }
        Remove-Item $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item $ExtractDir -ItemType Directory -Force | Out-Null
        $env:BIDCRAFT_SNAP = $Snapshot
        $env:BIDCRAFT_EXTRACT = $ExtractDir
        & $py -c "import os,zipfile; zipfile.ZipFile(os.environ['BIDCRAFT_SNAP']).extractall(os.environ['BIDCRAFT_EXTRACT'])"
        if ($LASTEXITCODE -eq 0) {
            $Inner = Get-ChildItem $ExtractDir -Directory | Select-Object -First 1
            if ($Inner) { $SyncSource = $Inner.FullName } else { $SyncSource = $ExtractDir }
            $synced = $true
            break
        }
        Write-Host "  解压失败（快照可能不完整），重试" -ForegroundColor Yellow
    }
    if (-not $synced) { Write-Host "[失败] 快照下载/解压失败" -ForegroundColor Red; exit 1 }
    Write-Host "  同步工作区..."
    & robocopy.exe $SyncSource "$PSScriptRoot" /E /XD ".git" ".deploy" "scripts/tools/tmp_out" /XF "升级生产.ps1" "版本记录.txt" "升级日志.txt" "gen2.txt" "gen_final.txt" "sme_prod_check.txt" /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -gt 7) { Write-Host "[失败] 工作区同步失败（robocopy exit $LASTEXITCODE）" -ForegroundColor Red; exit 1 }
    # 生产仓库原为 sparse-checkout（仅 README/SKILL/references/scripts）；zipball 全量同步后
    # 禁用 sparse 限制，保证 git add -A 能全量暂存（幂等，重复执行无害）
    git sparse-checkout disable 2>$null
    & git -c user.name='bidcraft-deploy' -c user.email='deploy@bidcraft.local' add -A
    if ($LASTEXITCODE -ne 0) { Write-Host "[失败] git add 失败（exit $LASTEXITCODE）" -ForegroundColor Red; exit 1 }
    & git -c user.name='bidcraft-deploy' -c user.email='deploy@bidcraft.local' commit -m "prod-sync $RemoteSha" --allow-empty | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "[失败] git commit 失败（exit $LASTEXITCODE），工作区已同步但未提交" -ForegroundColor Red; exit 1 }
    Write-Host ("  已同步 commit {0}" -f $RemoteSha.Substring(0,7))
}
Write-Host "== 1.5) 同步业务文档（生产本地补全 references）==" -ForegroundColor Cyan
# P0 修复（WorkBuddy 诊断）：SKILL.md 索引引用的 4 个业务文档因公网敏感治理被 .gitignore 排除、
# sparse-checkout 拿不到；生产本就是本地敏感环境（素材库/开发日志均在本地），故从开发仓库拷贝补齐，
# 不经 git，不影响"代码 100% 来自 GitHub"。源不存在时降级为警告，不阻断升级。
$DevRef = "E:\bidcraft_skill\references"
$BizDocs = @("M1-素材库-操作手册.md", "M2-模板库-需求对齐.md", "module-contracts.md", "产物反馈机制-需求对齐.md")
if (Test-Path $DevRef) {
    foreach ($doc in $BizDocs) {
        $src = Join-Path $DevRef $doc
        $dst = Join-Path "$PSScriptRoot\references" $doc
        if (Test-Path $src) {
            $need = $false
            if (-not (Test-Path $dst)) { $need = $true }
            elseif ((Get-Item $src).LastWriteTime -gt (Get-Item $dst).LastWriteTime) { $need = $true }
            if ($need) {
                Copy-Item $src $dst -Force
                Write-Host ("  [同步] {0}" -f $doc) -ForegroundColor Green
            }
        } else {
            Write-Host ("  [警告] 开发仓库缺 {0}，跳过" -f $doc) -ForegroundColor Yellow
        }
    }
} else {
    Write-Host ("  [警告] 开发仓库 {0} 不存在，跳过业务文档同步" -f $DevRef) -ForegroundColor Yellow
}
if ($behind -eq "0") {
    Write-Host ("已是最新版本：commit {0}" -f (git rev-parse --short HEAD))
    exit 0
}
Write-Host ("发现更新（commit {0}），快照同步完成，继续冒烟验证..." -f $RemoteSha.Substring(0,7))

Write-Host "== 2) 冒烟验证 ==" -ForegroundColor Cyan
# 探测生产 python：服务账户(NETWORK SERVICE)的 PATH 无 python；优先显式指定，其次常见系统路径
$py = $null
if ($env:BIDCRAFT_PYTHON) { $py = $env:BIDCRAFT_PYTHON }
if (-not $py) {
    foreach ($c in @("C:\Python312\python.exe", "C:\Python311\python.exe", "D:\anaconda3\python.exe")) {
        if (Test-Path $c) { $py = $c; break }
    }
}
if (-not $py) { $py = "python" }
& $py scripts\bidcraft.py --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ("[失败] 冒烟失败！请立即回滚：git reset --hard HEAD~{0}" -f $behind) -ForegroundColor Red
    exit 1
}
# 增强冒烟（P3b）：再跑一条只读子命令，验证 argparse 子命令挂载 + 存储层可初始化（零副作用）
$SmokeRoot = Join-Path $env:TEMP ("bidcraft_smoke_" + [Guid]::NewGuid().ToString("N"))
& $py scripts\bidcraft.py --root $SmokeRoot list-enterprises | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ("[失败] 子命令冒烟失败！请立即回滚：git reset --hard HEAD~{0}" -f $behind) -ForegroundColor Red
    Remove-Item $SmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}
Remove-Item $SmokeRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "== 3) 记录版本 ==" -ForegroundColor Cyan
$ver = $RemoteSha.Substring(0,7)
# 版本记录写入失败不阻断部署（仅警告）
try {
    $verLine = ("{0}  |  commit {1}  |  冒烟通过（快照同步）" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $ver)
    # 统一 UTF-8 无 BOM 追加（Add-Content 默认编码随 PowerShell 版本漂移——5.1=ANSI/7=UTF8，
    # 且 -Encoding utf8 追加会在内容中间插 BOM；用 .NET 无 BOM 追加跨版本一致）
    [System.IO.File]::AppendAllText("$PSScriptRoot\版本记录.txt", $verLine + [Environment]::NewLine,
                                    (New-Object System.Text.UTF8Encoding($false)))
} catch {
    Write-Host "[警告] 版本记录写入失败（不影响本次部署）：$($_.Exception.Message)" -ForegroundColor Yellow
}
Write-Host ("升级完成：commit {0}" -f $ver)
Write-Host "提示：若升级后发现问题，可回滚：git reset --hard <上一commit>"
