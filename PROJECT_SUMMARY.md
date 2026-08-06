# 鸿讯 HONGXUN · 论文监控工具

## 项目概述

面向科研人员的学术论文监控工具，支持 CrossRef 检索、六级摘要补全、AI 大模型翻译（英→中）、邮件推送、PDF 下载、文献书架管理、付费订阅与礼品券激活、macOS 开机自启、Windows 开机自启。

- **版本**：2.0.0
- **技术栈**：Python 3.11 + tkinter/ttk
- **入口**：`client/gui_app.py`
- **支持平台**：macOS 10.15+ / Windows 10/11 64位
- **macOS 启动**：双击 `macos/HONGXUN-TY.app`
- **Windows 启动**：双击 `dist/HONGXUN/HONGXUN.exe`（需先打包）

## 目录结构

```
HONGXUN-TY/
├── macos/
│   ├── HONGXUN-TY.app/         # macOS 应用包
│   └── 启动.command              # macOS 终端启动脚本
├── windows/
│   └── HONGXUN.spec            # Windows PyInstaller 打包配置
├── requirements.txt            # Python 依赖清单
├── tools/
│   ├── generate_icons.py       # 图标生成脚本（PIL 绘制线性图标）
│   └── build_journal_db.py     # 期刊数据库构建脚本（4295 本种子数据）
├── client/
│   ├── gui_app.py              # 主程序（Tkinter GUI）— 跨平台
│   ├── scheduler_daemon.py     # 独立调度守护进程
│   ├── gui/                    # UI 组件包（模块化）
│   │   ├── __init__.py
│   │   ├── theme.py            # 颜色/字体/图标常量 + ttk 样式表
│   │   ├── widgets.py          # 自定义控件（RoundedCard, ModernButton, ToggleSwitch 等）
│   │   ├── sidebar.py          # 侧栏（页面导航 NavItem + 任务卡片列表）
│   │   ├── dashboard.py        # 首页仪表盘（统计卡 + 最近文献 + 任务状态）
│   │   ├── library_view.py     # 三栏文献书架（列表+详情+元数据）
│   │   ├── journal_picker.py   # 期刊选择器（分类树 + 搜索 + 多选）
│   │   ├── journal_detail.py   # 期刊详情弹窗
│   │   └── journal_import.py   # 期刊批量导入
│   ├── core/
│   │   ├── __init__.py         # 模块统一导出
│   │   ├── abstract.py         # 六级摘要补全流水线（并行版）
│   │   ├── auto_updater.py     # 自动更新 + 公告广播（GitHub）
│   │   ├── code_protector.py   # 底层代码保护（MAC + 密码验证）
│   │   ├── config_manager.py   # 配置读写、输入校验、路径管理
│   │   ├── coupon_manager.py   # 礼品券管理 + 统一访问控制（登录/订阅/礼品券）
│   │   ├── email_sender.py     # 邮件发送（SSL 465 / TLS 587 双模式）+ 验证码
│   │   ├── engine.py           # 编排协调层（历史检索/增量检查/报告生成/AI翻译）
│   │   ├── journal_db.py       # 期刊数据库（SQLite 查询）
│   │   ├── journal_store.py    # 期刊库（种子灌入 + 收藏 + 浏览历史）
│   │   ├── library.py          # 文献书架数据模型（JSON 持久化）
│   │   ├── pdf_config.py       # PDF 下载配置
│   │   ├── pdf_fetcher.py      # PDF 多来源下载（Unpaywall/OpenAlex/arXiv/PMC/Sci-Hub）
│   │   ├── ref_formatter/      # 参考文献格式化引擎（6 格式 + AI 解析 + 交叉引用）
│   │   ├── search.py           # CrossRef 检索 + ISSN 解析 + cursor 分页
│   │   ├── session.py          # HTTP Session
│   │   ├── user_manager.py     # 邮箱+密码注册登录 + 会话 + 邀请码
│   │   ├── subscription.py     # 付费订阅（3 档套餐 + 占位支付接口）[锁定]
│   │   └── translator.py       # AI 大模型翻译（DeepSeek/千问/智谱/豆包/Kimi/MiniMax）
│   ├── data/                   # JSON 持久化（任务/邮箱/许可/推送记录/调度状态/期刊库）
│   ├── logo/
│   │   ├── zm.png              # 应用图标
│   │   ├── ztl.png             # 标题栏图标
│   │   ├── qdy.png             # 启动页图片
│   │   └── icons/              # PIL 生成的 24×24 线性图标 PNG（两色变体）
│   └── output/
│       └── unsent/             # 邮件发送失败的附件备份
└── docs/                       # 文档目录
```

## 核心功能

### 页面导航架构（v2.0.0）

应用采用「左侧栏 + 右侧页面容器」的单窗口布局，侧栏顶部为 4 个页面导航项：

| 页面 | 说明 |
|------|------|
| 📊 概览 | DashboardView：统计卡 + 最近文献 + 任务状态 + 激活状态 + 礼品券/订阅入口 |
| 📋 监控任务 | 任务表单：任务名、期刊选择器、关键词、日期范围 |
| 📚 文献书架 | LibraryView：三栏布局（列表 + 详情 + 元数据） |
| ✏️ 格式助手 | RefFormatterView：参考文献格式化 + AI 自定义格式解析 |
| ⚙ 设置 | 每日推送 + 邮箱配置 + AI 翻译 + PDF 下载 + 激活状态 |

### 论文检索
- CrossRef API，按期刊 + 时间范围检索
- **Cursor 深度分页**：突破 CrossRef 单页 1000 条限制，自动翻页
- **按周切割逐周检索**：时间范围自动按周切割，逐周检索后合并去重（降低漏检）
- **支持检索取消**：检索过程中可随时点击「取消」按钮中止
- 关键词过滤流程（仅历史检索）：检索 → 摘要补全 → 用补全的标题+摘要匹配关键词
- **每日推送不按关键词过滤**：检索期刊所有论文，补全摘要后全部推送
- 六级摘要补全：OpenAlex → Semantic Scholar（DOI）→ Tavily 搜索引擎
- 输出格式：DOCX / DOC / TXT / MD

### 智能期刊选择（v2.0.0）
- 内置中科院 1/2 区 **4295 本期刊库**，按「大类 → 小类 → 分区」三级分类树可视化选择
- 支持搜索过滤、多选、收藏、详情查看、批量导入（RIS/BIB/CSV/XLSX）
- 支持手动输入库外期刊
- SQLite 存储（`journals.db`），首次从种子文件 `journals_seed.json` 灌入

### AI 大模型翻译（v2.0.0）
- 支持多家 LLM 大模型（OpenAI 兼容接口）：**DeepSeek / 千问 Qwen / 智谱 GLM / 豆包 / Kimi / MiniMax / 自定义**
- 在「设置 → AI 翻译」中配置厂商 + API Key + Base URL + Model，支持「测试连接」
- API Key 持久化到 `client/.env`，厂商配置到 `app_config.json`
- 检索报告与推送邮件中均包含翻译结果（中英双语）
- **失败中断**：API 调用失败（401/402/403/429）时抛异常 → 中断检索/推送 → 弹窗提示
- **断点续传**：重启后先检测 API 可用性，可用则继续，不可用则弹窗确认

### PDF 下载（v2.0.0）
- 多来源回退下载：Unpaywall → OpenAlex → arXiv → PMC → 出版社直连
- 可选 **Sci-Hub 增强**（开启需阅读版权风险提示 + 5 秒倒计时确认）
- 文件名：`首作者姓_年份_短标题.pdf`，默认保存到 `~/Downloads/HONGXUN-PDF/`

### 报告生成（DOCX）
- 西文 Times New Roman + 中文宋体 SimSun，5号字（10.5pt），固定行间距 18pt
- 使用文本行格式代替表格，大幅减少 XML 体积
- 中英双语内容（标题 + 摘要）

### 邮件推送
- 任意 SMTP（QQ邮箱/163/126/Gmail/新浪/Outlook/189 等）
- SMTP 供应商下拉菜单按邮箱类别分组，自动配置服务器地址
- **多端口自动回退**：同一供应商的多个端口依次尝试（465 → 587）
- 发件邮箱 + SMTP 授权码（可显/隐）+ 最多 5 个收件人（动态增删）
- **每日推送时间可配置**（`app_config.json` 的 `push_time`，默认 08:00）
- **支持最多 5 个并行任务**
- 无论文时 GUI 弹窗提示

### 邮件发送失败处理
- 检索完成后先保存 DOCX 附件到 `output/unsent/`
- 发送失败时写入 `pending_email.json` 记录未发送文件清单
- 邮箱设置区提供「再发送」按钮：直接读取本地附件重发

### 独立调度守护进程
- 与 GUI 进程解耦，GUI 关闭后继续运行
- PID 文件 + 停止标记实现进程间通信
- **macOS 开机自启**（launchd）
- **Windows 开机自启**（注册表 HKCU\…\Run）

### 付费订阅系统（v2.0.0，锁定代码）
- **3 档订阅套餐**（扫码支付，个人开发者免签约聚合支付）：

| 档位 | 现价 | 有效期 | 类型 |
|------|:----:|:------:|:----:|
| 1 个月 | **¥9.9** | 30 天 | 限时 |
| 1 年 | **¥99** | 365 天 | 限时 |
| 永久 | **¥299** | 永久 | 永久激活 |

- 订阅弹窗：三档套餐卡片 + 蓝色高亮价格卡 + 删除线原价 + 折扣徽章 + 底部保障信息
- 选中套餐后点「立即解锁」弹出二维码（当前为占位二维码，预留支付平台替换接口）
- 支付成功自动激活并开始计时，永久档写 `permanent: True`，到期时间写极远（2099-12-31）
- **订阅代码经 code_protector 锁定**（HONGXUN-LOCKED，仅本机可查看/修改）
- 支付接入说明见 `subscription.py` 的 `PAYMENT_ADAPTER` 区块（虎皮椒/易支付等免签约平台）

### 邮箱+密码注册登录制（v2.0.0）
- **注册**：邮箱（用户名）+ 验证码 + 密码（≥6位，含数字+字母）；同一邮箱只能注册一次
- **验证码**：经内置 QQ 邮箱 SMTP 发送（不依赖用户配置），10 分钟有效，60 秒防重发
- **密码加密**：加盐 PBKDF2 哈希存储（管理员/仓库均看不到明文）
- **登录**：邮箱+密码验证，本地 session 持久化；登录后即可使用免费版功能
- **游客模式**：可浏览界面，不能执行任何功能（检索/保存/导出/PDF下载/格式化均需登录）
- **账号可见性**：注册邮箱写入 GitHub 注册表 users 列表（密码不可见），管理员可查看账号
- **邀请码**：用户首次生成专属 8 位唯一码（字母+数字），被邀请人填码注册 → 邀请人 +1 个月全功能

### 统一访问控制（v2.0.0）
- **免费版（登录即可用）**：检索（每次 1 个任务）、书架（最多 50 篇）、格式助手 GB/T、3 年检索跨度
- **高级功能**（需订阅）：AI 翻译、全部格式、自定义 AI 解析、邮件推送、Sci-Hub 增强
- 判断优先级：订阅激活（全功能）→ 礼品券激活（全功能）→ 已登录（免费版）
- **3 天宽限期**：订阅/礼品券到期后宽限期内仍可用，宽限期后彻底锁定
- 到期时间显示具体日期（如 `2026-08-30`），永久激活显示「永久」

### 论文格式修改助手（v2.0.0，新增）
- **6 种标准格式转换**：GB/T 7714 / IEEE / APA 7th / Chicago / MLA / Harvard
- 左右分栏 UI + 左侧步骤导航（选择文件 → 选择格式 → 选项设置 → 开始处理，完成态持久化）
- **交叉引用超链接**（Ctrl+Click 跳转）+ 角标上标 + 按引用顺序重排 + 连续引用合并
- 自动备份原文件、格式校验（悬空引用/编号不连续检测）
- **AI 自定义格式解析**：上传期刊格式要求文件（PDF/Word/文本）→ LLM 解析 → 确认套用
- 文件提取：PDF 用 markitdown 转 Markdown，Word 用 python-docx，文本直读

### 礼品券激活（与订阅并存）
- 24位编码（XXXX-XXXX-XXXX-XXXX-XXXX-XXXX），含 HMAC 防伪签名
- 支持 3M / 6M / 12M / 24M 有效期类型（多类型券，GitHub 后端）
- 设备绑定（MAC 地址）
- **仅首页保留礼品券入口**，受限板块弹窗引导订阅

### 底层代码保护
- 12 个 Python 源文件受保护（含 HONGXUN-LOCKED 标记）
- **本机 MAC 自动授权**（`ac:de:48:00:11:22`）
- 非本机设备需密码解锁
- 保护文件含 `core/subscription.py`（订阅支付逻辑）

### 自动更新 + 公告广播
- GitHub Release 更新机制，启动时检查版本
- 公告广播：从仓库读取 `notice.json`，按 `msg_id` 去重弹窗通知

## UI 架构

```
client/
└── gui/                     # UI 组件包
    ├── theme.py             # 颜色/字体/图标/设计token/smtp常量 + ttk 样式表
    ├── widgets.py           # 自定义 Canvas 控件库（含 IconButton/LinkButton/Toast/AppState）
    ├── sidebar.py           # 侧栏（页面导航 + 任务卡片）
    ├── dashboard.py         # 首页仪表盘
    ├── library_view.py      # 三栏文献书架
    ├── ref_formatter_view.py # 论文格式修改助手（步骤导航 + AI 解析流程）
    ├── journal_picker.py    # 期刊选择器
    ├── journal_detail.py    # 期刊详情
    └── journal_import.py    # 期刊导入
```

### 颜色体系（v2.0.0 冷色 Slate 基调）

| 角色 | 值 | 用途 |
|------|------|------|
| **primary** | `#3B82F6` | 主色（Blue-500） |
| primary_2 | `#60A5FA` | 渐变起始（Blue-400） |
| primary_hover | `#2563EB` | 悬停（Blue-600） |
| primary_active | `#1D4ED8` | 按下（Blue-700） |
| primary_light | `#DBEAFE` | 选中/高亮背景 |
| **success** | `#10B981` | 成功/运行中 |
| **warning** | `#F59E0B` | 警告 |
| **danger** | `#EF4444` | 错误/排除 |
| **bg_page** | `#F8FAFC` | 页面背景（Slate-50） |
| **bg_card** | `#FFFFFF` | 卡片背景 |
| **sidebar_bg** | `#F1F5F9` | 侧栏背景（Slate-100） |
| text_title | `#0F172A` | 标题（Slate-900） |
| text_body | `#1E293B` | 正文（Slate-800） |
| text_secondary | `#64748B` | 次要文字（Slate-500） |
| text_hint | `#94A3B8` | 占位符（Slate-400） |

### 字体系统

| 层级 | 字号（macOS） | 字重 | 用途 |
|------|:-------------:|:----:|------|
| FONT_METRIC | 32pt | Bold | 仪表盘数字 |
| FONT_DISPLAY | 32pt | Bold | 大标题 |
| FONT_TITLE | 15pt | Bold | 页面标题 |
| FONT_HEADING | 13pt | Bold | 卡片标题 |
| FONT_BODY | 13pt | Normal | 正文 |
| FONT_LABEL | 13pt | Bold | 表单标签 |
| FONT_CAPTION | 11pt | Normal | 辅助文字 |
| FONT_MONO | 13pt | Normal | DOI/代码 |

- 平台适配：Windows 基准字号 9pt，macOS 13pt
- 响应式缩放：8~18pt 区间，上限 1.35x

## 自定义控件库

| 控件 | 说明 | 技术 |
|------|------|------|
| **RoundedCard** | 圆角矩形 + 阴影 + 边框，支持 fit_content/hover 抬升 | `tk.Canvas` + `create_polygon` |
| **ModernButton** | 圆角按钮，hover/press 状态，防黑底透色 | `tk.Canvas` |
| **ModernEntry** | 统一输入框，placeholder + focus 边框 | `tk.Entry` |
| **ModernScrollbar** | 圆角滚动条，内容放不下时才显示滑块 | `tk.Canvas` |
| **StatusPill** | 三色状态胶囊（待读/已读/排除） | `tk.Canvas` |
| **ToggleSwitch** | iOS 风格开关，6 步滑动动画 | `tk.Canvas` |
| **SkeletonLoader** | 脉冲灰条骨架屏 | `tk.Canvas` + `after` 循环 |
| **EmptyState** | 居中空态（图标+标题+副标题） | `tk.Frame` |
| **IconCache** | 图标缓存，PNG/PIL/emoji 回退 | — |

## 键盘快捷键

| 平台 | 新建任务 | 保存任务 |
|------|---------|---------|
| macOS | `Cmd+N` | `Cmd+S` |
| Windows | `Ctrl+N` | `Ctrl+S` |

## 启动流程

### macOS
1. 双击 `macos/HONGXUN-TY.app` → 自动运行 `python3 client/gui_app.py`
2. 或双击 `macos/启动.command` → 终端运行
3. 启动后依次：激活检查 → 守护进程状态 → 试用期状态 → 到期检测 → LLM API 检测 → 推送结果轮询

### Windows（源码运行）
1. `cd client && python gui_app.py`

### Windows（打包后运行）
1. 在 Windows 上运行 `windows/build_exe.py`（或 `build_exe.bat`）
2. 输出 `dist/HONGXUN/HONGXUN.exe`
3. 双击运行，无需安装 Python

## 版本历史

### v2.0.0（当前）
**架构与功能大版本升级：**
- **页面导航架构**：侧栏 4 页面导航（概览/监控/书架/设置）+ DashboardView 首页仪表盘
- **智能期刊选择器**：4295 本期刊库，三级分类树 + 搜索 + 多选 + 收藏 + 详情 + 批量导入
- **PDF 下载**：多来源回退 + Sci-Hub 增强（风险提示 + 5 秒确认）
- **AI 大模型翻译**：多家厂商接入（DeepSeek/千问/智谱/豆包/Kimi/MiniMax），配置弹窗 + 测试连接 + 失败中断 + 断点续传
- **付费订阅系统**：4 档套餐扫码订阅（占位支付接口），与礼品券并存
- **统一有效期检测**：4 个受限板块 + 3 天宽限期 + 启动自动检测 + 到期时间具体日期显示
- **冷色 Slate 主题**：主色 Blue-500、圆润控件、卡片悬浮效果
- **推送时间可配置**：每日推送时间可在设置中调整

### v1.5.0
- 状态图标（○/▲/★）+ 自动标记已读 + DOI 打开浏览器
- 公告推送系统（Gitee notice.json）+ 更新检测优化

### v1.3.x
- GUI 架构重构：拆分 gui/ 组件包 + 圆角卡片系统 + 三栏文献书架

## 依赖

```bash
pip install -r requirements.txt
```

requirements.txt：`requests>=2.28.0`、`python-docx>=1.1.0`、`selenium>=4.15.0`、`Pillow>=9.0.0`
