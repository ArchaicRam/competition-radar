# 竞赛情报监控 · 大学生计算机竞赛聚合推送

面向高校计算机社团项目部：**每天自动扫描各平台"正在进行/即将开始"的计算机类竞赛**，
发现新比赛就推送到飞书群，并自动维护一份 CSV 台账。

覆盖：阿里云天池、DataFountain、牛客、科大讯飞 AI 开发者大赛、Kaggle、赛氪
（企业/政府主办的赛事为主，不是蓝桥杯那种大众榜）。

---

## 快速开始

```bash
# 1. 复制配置模板（config.json 含飞书 Webhook 密钥，不会入库）
copy config.example.json config.json
# Linux/macOS: cp config.example.json config.json

# 2. 编辑 config.json，把 feishu_webhook 换成你飞书群的机器人地址
#    （飞书群 -> 设置 -> 群机器人 -> 添加机器人 -> 自定义机器人 -> 复制 Webhook）

# 3. 先试跑（只打印，不推送、不改状态）
python run_daily.py --dry-run

# 4. 发一条测试消息到飞书群，确认机器人通了
python run_daily.py --test-notify

# 5. 正式跑一次（抓取 -> 增量对比 -> 推送 -> 落库 -> 导出 CSV）
python run_daily.py --export-csv
```

> 只依赖 Python 标准库，无需 pip install（`requirements.txt` 仅备参考）。

---

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `feishu_webhook` | 飞书群机器人 Webhook（必填，否则不会推送） |
| `feishu_secret` | 机器人创建时若勾选"签名校验"，填这里的密钥（不勾就留空） |
| `sources` | 启用的平台列表：`tianchi, datafountain, nowcoder, xfyun, kaggle, saikr` |
| `only_new` | `true` 只推新发现的比赛（配合 `send_table_daily` 时用于高亮判断） |
| `digest_when_no_new` | `false` 且未开表格推送时，当天没有新比赛也发一条"今日无新" |
| `send_table_daily` | `true`（默认）：每天发一张**情报日报卡片**（摘要+今日新增+即将截止+数据来源） |
| `max_table_rows` | 保留兼容字段（新版卡片不再用大表格，明细都在 Excel 里） |
| `excel_file` | Excel 台账输出路径（默认 `data/competitions.xlsx`） |
| `excel_link` | 可选：Excel 的在线下载链接（如 GitHub raw 链接），配置后在卡片里显示可点链接 |
| `feishu_sheet_url` | 可选：**飞书在线表格** URL，配置后每天自动同步到该表，卡片里显示"查看在线表格"链接 |
| `lark_profile` | lark-cli 的应用 profile 名（默认 `jingsai`，即"竞赛雷达"应用） |
| `official_keywords` | 可选：覆盖"教育部认定赛事"识别关键词（默认内置常见 A 类赛事名单） |
| `llm_api_key` | **DeepSeek API Key**（platform.deepseek.com 获取），AI 情报员/日报解读的开关；留空则 AI 模块全部跳过 |
| `llm_base_url` | 默认 `https://api.deepseek.com`，其它 OpenAI 兼容服务可改 |
| `llm_model` | 默认 `deepseek-chat` |
| `ai_discover` | `true`：启用"AI 情报员"，扫描 `seed_sources` 非接口型来源 |
| `ai_digest` | `true`：启用"AI 今日看点"，卡片里多一段当日解读 |
| `seed_sources` | AI 情报员的种子源列表 `[{"name":"站点名","url":"页面地址"}]`，可随意增删（官网公告/聚合站/揭榜挂帅页/高校就业网都行） |
| `max_items_per_push` | 单次推送最多列出的比赛数 |
| `deadline_alert_days` | 截止日期在 N 天内的比赛会加"⏰x天后截止"标记 |
| `data_file` | 增量状态文件（默认 `data/state.json`，需要入库以便跨天去重） |
| `kaggle_username` / `kaggle_key` | Kaggle 账号（见下文 Kaggle 说明），也可用环境变量 |

环境变量可覆盖部分配置（方便 GitHub Actions 免配置文件）：

- `FEISHU_WEBHOOK`、`FEISHU_SECRET`、`SOURCES`、`DATA_FILE`、`HTTP_TIMEOUT`
- `KAGGLE_USERNAME`、`KAGGLE_KEY`、`LLM_API_KEY`

---

## 命令行

```bash
python run_daily.py                  # 完整运行（每天发比赛总览卡片）
python run_daily.py --dry-run        # 只打印，不推送不改状态
python run_daily.py --test-notify    # 飞书测试消息
python run_daily.py --demo           # 发一张演示卡片（含高亮/官方赛事/即将截止示例）
python run_daily.py --reset          # 清空"已见"记录，下次全部视为新比赛
python run_daily.py --sources tianchi,datafountain   # 只抓指定平台
python run_daily.py --export-csv     # 导出台账 data/competitions.csv（Excel 可开）
```

## 每日推送长什么样

每天发一张**情报日报卡片** + 同步**飞书在线表格** + 生成**本地 Excel 台账**：

- 表头：`📡 竞赛雷达 · 情报日报（今日新增 N）`，有新比赛时表头变红
- 摘要：共 N 场进行中 ｜ 教育部认定赛事 X 场 ｜ 今日新增 M
- **今日新增**：红色加粗清单（带报名链接）
- **即将截止**：N 天内截止的比赛清单（⏰x天后）
- **数据来源**：天池 / DataFountain / 牛客 / 讯飞 / Kaggle 各自的来源地址
- **在线表格**：卡片底部"📊 查看在线表格"可点链接（配了 `feishu_sheet_url` 时）

### 飞书在线表格（推荐，群成员点开即看）

配置 `feishu_sheet_url` 后，每次运行自动把全部比赛同步到飞书电子表格：
- 列：类别 / **含金量** / 赛名 / 主办方 / 类型 / 开始日期 / 截止日期 / 阶段 / 奖金 / 来源 / 链接
- **含金量**：高=红、中=橙、低=绿（条件格式自动上色）；
  AI 发现条目由 AI 评级，其余按主办方/名称规则推算
- 官方赛事在前、同一主办方聚合、按截止日期排序
- **今日新增行红底红字**，次日同步时自动清除旧高亮
- 表头加粗、列宽已优化；组织内成员有链接即可查看

**前置**：需要 lark-cli（`npx @larksuite/cli@latest install`）和飞书应用 profile
（`lark-cli config init --app-id <ID> --app-secret-stdin --name <profile>`），
应用需开通 sheets/drive 权限。同步用 bot 身份，无需登录。
> 注：同步时会清空并重写表格内容（`+cells-clear` 属高风险写操作，
> 已获用户授权自动带 `--yes`，仅作用于本系统的总览表）。

### Excel 台账说明（data/competitions.xlsx）

- 列：**类别 / 赛名 / 主办方 / 类型 / 开始日期 / 截止日期 / 阶段 / 奖金 / 来源 / 链接**
- **今日新增行红底红字**，次日自动恢复普通样式
- **教育部认定赛事**比赛的"类别"单元格黄底标注，且**排在表格最前**
- 同一主办方的比赛**聚合在一起**（主办方名称做了归一化，如去掉"有限公司"后缀）
- 第二张 sheet"数据来源"记录各平台来源地址与更新说明
- 排序规则：教育部认定赛事优先 → 同一主办方聚合 → 截止日期升序

### AI 模块（可选，需配置 llm_api_key）

配置 DeepSeek API Key 后启用两个能力：

1. **AI 情报员（ai_discover）**：固定平台接口覆盖不到的来源——企业官网公告、
   黑客松页面、揭榜挂帅/众包平台、赛事聚合站、高校就业网——靠 AI 从页面文本里
   提炼比赛/需求征集（标题/主办方/类型/截止/奖励/链接/含金量），并入总表，
   "来源"列标注 **AI发现·站点名**，状态标"待核实"（建议人工复核后再报名）。
   - **含金量为"低"（商业营销、付费参赛、野鸡主办方）的直接过滤**，不入表
   - 报名链接优先匹配页面内的真实公告页（锚点匹配），不再是聚合站首页
   - 种子源在 `seed_sources` 里随意增删，任何能打开的公告页都能当种子。
2. **AI 今日看点（ai_digest）**：每天把当日新增写成 ≤130 字的"今日看点"
   （最值得关注的、类型分布、给社团的建议），显示在卡片顶部。

> 抓取依然全在本地/CI 执行；LLM 只负责"读页面+提炼"和"写看点"两件事。
> AI 发现的结果是线索，不是权威信息，报名前请以原链接页面为准。

## 数据质量自检

每次扫描会对数据做校验，异常行直接拦截并记日志（不会进表）：
- 标题为空、日期格式异常、占位日期（1999/1970 等）
- 开始时间晚于截止时间（数据错误）
- 牛客 OJ 赛显示到分钟（如 `08-17 13:00 - 17:00`），避免"同一天还显示未开始"的困惑

---

## 各平台支持情况

| 平台 | 数据来源 | 说明 |
|---|---|---|
| **天池** tianchi.aliyun.com | 官方接口 `GET /v3/proxy/competition/api/race/page` | 需先访问页面拿 cookie + CSRF 头；数据中心 IP 可能被 403 拦截，拦截时自动跳过不报错 |
| **DataFountain** datafountain.cn | 官方接口 `/api/competitions` | 稳定 |
| **科大讯飞** challenge.xfyun.cn | 官方接口 `/2020/ai-contest/api/contests/contests-list` | 稳定，含全部赛事 |
| **Kaggle** kaggle.com | 官方 API v1 `/api/v1/competitions/list` | **需要 Kaggle 账号**：kaggle.com -> Settings -> API -> Create New Token，把 username/key 填入配置；未配置则自动跳过 |
| **牛客** nowcoder.com | 全网 OJ 比赛日历官方接口 `/acm/calendar/contest` | 稳定；含牛客周赛/挑战赛 + AtCoder/Codeforces/LeetCode 等算法赛 |
| **赛氪** saikr.com | — | **暂未接入**：前端为 SPA 且竞赛列表接口未公开，可手动浏览 [saikr.com/contests](https://www.saikr.com/contests) |

### 飞书机器人怎么建（不需要在开放平台发布任何版本）

> 我们用是飞书**群机器人（自定义机器人 Webhook）**，不是开放平台的企业自建应用，
> 所以**没有"发布版本"这回事**：不用建应用、不用申请权限、不用审核。

1. 打开你的飞书群 -> 右上角"设置" -> **群机器人** -> **添加机器人**
2. 选 **自定义机器人** -> 起个名字（如"竞赛情报"）-> 创建
3. 创建时有三项安全设置：
   - **自定义关键词**：可以不设；若设了，推送文本必须包含该关键词（建议设"竞赛情报"）
   - **签名校验**：可以不勾；若勾了，把"密钥"填进 `config.json` 的 `feishu_secret`（代码已支持加签）
   - **IP 白名单**：本机跑就填本机公网 IP；用 GitHub Actions 就别设（服务器 IP 会变）
4. 复制 Webhook 地址（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxx`），粘进 `config.json`
5. `python run_daily.py --test-notify` 验证

---

## 定时任务（两种任选其一）

### 方式 A：GitHub Actions（推荐，不用一直开电脑）

> GitHub Actions **不是云服务器**：它是免费的计划任务，每天到点临时开一台虚拟机
> 跑完即销毁，不常驻、不收费、不用运维。云服务器（VPS）是常驻机器，要花钱买，
> 对本项目属于杀鸡用牛刀。

1. 把本项目推到 GitHub 仓库（`data/` 目录会跟着走，它是增量去重的依据）
2. 仓库 Settings -> Secrets and variables -> Actions，添加：
   - `FEISHU_WEBHOOK` = 你的 Webhook
   - （可选）`KAGGLE_USERNAME` / `KAGGLE_KEY`
3. 完成。每天北京时间 06:00 自动扫描，新比赛推送到飞书群，
   并把 `data/state.json`、`data/competitions.csv` 自动提交回仓库。

> 也可以手动触发：Actions 页面 -> "daily-competition-scan" -> Run workflow。

### 方式 B：Windows 任务计划程序（本机跑）

**命令行一键创建（推荐）**：打开 PowerShell（不用管理员），粘贴执行：

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"D:\find_competition\run_daily.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At 06:00
Register-ScheduledTask -TaskName "竞赛情报-每日扫描" -Action $action -Trigger $trigger -Description "每天6:00扫描竞赛并推送飞书" -Force
```

验证：`Get-ScheduledTask -TaskName "竞赛情报-每日扫描"`；删除：`Unregister-ScheduledTask -TaskName "竞赛情报-每日扫描" -Confirm:$false`

**或用图形界面**：
1. `Win+R` 输入 `taskschd.msc` 打开任务计划程序
2. 创建任务 -> 触发器：每天 06:00 -> 操作：启动程序
   - 程序：`powershell.exe`
   - 参数：`-ExecutionPolicy Bypass -File "D:\find_competition\run_daily.ps1"`
3. 日志写在 `logs\daily.log`，方便排查

---

## 数据与增量逻辑

- `data/state.json`：所有见过的比赛（按 `平台:ID` 去重）。
  每次运行对比本次抓取结果，**只推送"新出现"的比赛**；
  截止/奖金/状态有变化的比赛会以"🔄 有更新"单独列出。
- `data/competitions.csv`：全部已知比赛台账，按截止日期排序，
  Excel/WPS 直接打开（UTF-8 BOM）。

---

## 扩展新平台

1. 在 `src/fetchers/` 下新建 `xxx.py`，继承 `BaseFetcher`，实现 `fetch()` 返回 `Competition` 列表
2. 在 `src/fetchers/__init__.py` 的注册表里加上 `"xxx": XxxFetcher`
3. 把 `xxx` 加进 `config.json` 的 `sources`

字段约定见 `src/models.py`；抓取失败抛异常即可，runner 会统一记录；
不想报错想跳过时抛 `FetcherSkip`。

---

## 已知限制

- 天池反爬较严：在云服务器/数据中心 IP 上可能 403（自动跳过、不算失败），家庭宽带一般正常
- Kaggle 需要账号配置；不配就自动跳过
- 赛氪接口未公开，暂未接入；其内容以数学建模/英语/创新创业等综合竞赛为主，与"计算机企业赛"定位重叠度低
- **飞书"自定义机器人"（webhook）不能直接发送文件**（API 实测 `msg type file not support`）。
  已用**飞书在线表格 + 卡片链接**方案替代（群成员点链接查看/筛选/排序），
  本地 Excel 台账仍每日生成；若确实需要把文件发进群，需走自建应用上传文件接口
- 平台改版可能导致个别抓取器失效，`--dry-run` 可快速自检
- 首次运行会把当前所有进行中的比赛视为"新比赛"（数量较多属正常），之后只推增量
- 本工具聚焦"企业/官方平台发布的竞赛"，教育部认定赛事（蓝桥杯等）建议另外
  关注学校教务处通知（那些本来就是通过学校渠道发布的）

