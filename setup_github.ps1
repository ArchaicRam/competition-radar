# 竞赛雷达 · GitHub Actions 一键配置脚本
# 作用：安装 GitHub CLI -> 登录 -> 创建私有仓库 -> 推送 -> 自动配置全部 Secrets
# 用法：在 PowerShell 中执行  powershell -ExecutionPolicy Bypass -File setup_github.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

# ---------- 1. 安装 GitHub CLI ----------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host ">> 安装 GitHub CLI（winget）..."
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!! winget 安装失败，请手动安装 https://cli.github.com/ 后重跑本脚本" -ForegroundColor Red
        exit 1
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
Write-Host ">> GitHub CLI 就绪：$(gh --version | Select-Object -First 1)"

# ---------- 2. 登录 ----------
$authed = $false
try { gh auth status *> $null; $authed = ($LASTEXITCODE -eq 0) } catch { $authed = $false }
if (-not $authed) {
    Write-Host ">> 请在浏览器中完成 GitHub 登录（登录后回到本窗口）..."
    gh auth login --web --git-protocol https
}

# ---------- 3. 建私有仓库并推送 ----------
if (-not (git remote -v)) {
    Write-Host ">> 创建私有仓库 competition-radar 并推送..."
    gh repo create competition-radar --private --source . --remote origin --push
}

# ---------- 4. 配置 Secrets（从本地配置自动读取，无需手打） ----------
Write-Host ">> 配置仓库 Secrets..."
# 密钥一律通过管道（stdin）传给 gh，避免出现在进程命令行 / PowerShell 历史里
function Set-Secret([string]$Name, [string]$Value) {
    if (-not $Value) { return }
    $Value | gh secret set $Name
    if ($LASTEXITCODE -ne 0) { throw "gh secret set $Name 失败" }
}
$cfg = Get-Content config.json -Raw -Encoding UTF8 | ConvertFrom-Json
Set-Secret FEISHU_WEBHOOK $cfg.feishu_webhook
Set-Secret FEISHU_SECRET  $cfg.feishu_secret
Set-Secret FEISHU_CHAT_ID $cfg.feishu_chat_id
Set-Secret FEISHU_SHEET_URL $cfg.feishu_sheet_url
Set-Secret LLM_API_KEY    $cfg.llm_api_key
Set-Secret KAGGLE_USERNAME $cfg.kaggle_username
Set-Secret KAGGLE_KEY     $cfg.kaggle_key
$larkCfg = Join-Path $env:USERPROFILE ".lark-cli\config.json"
if (Test-Path $larkCfg) {
    $lark = Get-Content $larkCfg -Raw -Encoding UTF8 | ConvertFrom-Json
    $app = $lark.apps | Where-Object { $_.name -eq "jingsai" } | Select-Object -First 1
    if ($app) {
        Set-Secret LARK_APP_ID $app.appId
        Set-Secret LARK_APP_SECRET $app.appSecret
    }
}

# ---------- 5. 完成 ----------
Write-Host ""
Write-Host "✅ 完成！" -ForegroundColor Green
$user = gh api user -q .login
Write-Host "  仓库: https://github.com/$user/competition-radar"
Write-Host "  接下来：在仓库 Actions 页面手动触发一次 daily-competition-scan 验证"
Write-Host "  之后每天 06:00（北京时间）自动运行，你的电脑关机也能跑"
