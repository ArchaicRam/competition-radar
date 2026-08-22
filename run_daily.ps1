# -*- coding: utf-8 -*-
# 每天自动运行一次（配合 Windows"任务计划程序"使用，详见 README）
# 日志写到 logs\daily.log，出错了也能查；退出码透传给计划任务判断成败
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$log = "logs\daily.log"
$start = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$start] ===== 开始扫描 =====" | Tee-Object -FilePath $log -Append
python run_daily.py --export-csv 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
$end = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$end] ===== 扫描结束（exit=$code）=====" | Tee-Object -FilePath $log -Append
exit $code
