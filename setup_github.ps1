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
$cfg = Get-Content config.json -Raw -Encoding UTF8 | ConvertFrom-Json
if ($cfg.feishu_webhook) { gh secret set FEISHU_WEBHOOK -b $cfg.feishu_webhook }
if ($cfg.feishu_secret)  { gh secret set FEISHU_SECRET -b $cfg.feishu_secret }
if ($cfg.feishu_sheet_url) { gh secret set FEISHU_SHEET_URL -b $cfg.feishu_sheet_url }
if ($cfg.llm_api_key)    { gh secret set LLM_API_KEY -b $cfg.llm_api_key }
if ($cfg.kaggle_username){ gh secret set KAGGLE_USERNAME -b $cfg.kaggle_username }
if ($cfg.kaggle_key)     { gh secret set KAGGLE_KEY -b $cfg.kaggle_key }
$larkCfg = Join-Path $env:USERPROFILE ".lark-cli\config.json"
if (Test-Path $larkCfg) {
    $lark = Get-Content $larkCfg -Raw -Encoding UTF8 | ConvertFrom-Json
    $app = $lark.apps | Where-Object { $_.name -eq "jingsai" } | Select-Object -First 1
    if ($app) {
        gh secret set LARK_APP_ID -b $app.appId
        gh secret set LARK_APP_SECRET -b $app.appSecret
    }
}

# ---------- 5. 完成 ----------
Write-Host ""
Write-Host "✅ 完成！" -ForegroundColor Green
$user = gh api user -q .login
Write-Host "  仓库: https://github.com/$user/competition-radar"
Write-Host "  接下来：在仓库 Actions 页面手动触发一次 daily-competition-scan 验证"
Write-Host "  之后每天 06:00（北京时间）自动运行，你的电脑关机也能跑"
