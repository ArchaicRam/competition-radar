# -*- coding: utf-8 -*-
# 每天自动运行一次（配合 Windows"任务计划程序"使用，详见 README）
# 日志写到 logs\daily.log，出错了也能查
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$stamp] ===== 开始扫描 ====="
python run_daily.py --export-csv 2>&1 | Tee-Object -FilePath "logs\daily.log" -Append
Write-Output "[$stamp] ===== 扫描结束 ====="
