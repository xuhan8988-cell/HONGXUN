# 鸿讯 HONGXUN · 论文监控工具（郑州大学定制版）

## 项目概述

面向科研人员的学术论文监控工具，支持 CrossRef 检索、六级摘要补全、邮件推送、macOS 开机自启、Windows 开机自启。

- **版本**：1.3.2-ZZU
- **技术栈**：Python 3.11 + tkinter/ttk
- **入口**：`client/gui_app.py`
- **支持平台**：macOS 10.15+ / Windows 10/11 64位
- **macOS 启动**：双击 `HONGXUN-ZZU.app`
- **Windows 启动**：双击 `dist/HONGXUN/HONGXUN.exe`（需先打包）
- **版本**：1.3.2-ZZU

## 目录结构

```
HONGXUN-ZZU/
├── HONGXUN-ZZU.app/             # macOS 应用包
├── HONGXUN.spec                 # PyInstaller 打包配置
├── build_exe.bat                # Windows 一键打包脚本
├── requirements.txt             # Python 依赖清单
├── 启动.command                  # macOS 终端启动脚本
├── tools/
│   └── generate_icons.py        # 图标生成脚本（PIL 绘制线性图标）
├── client/
│   ├── gui_app.py               # 主程序（Tkinter GUI）— 跨平台
│   ├── scheduler_daemon.py      # 独立调度守护进程
│   ├── gui/                     # UI 组件包（重构后拆分）
│   │   ├── __init__.py
│   │   ├── theme.py             # 颜色/字体/图标常量 + ttk 样式表
│   │   ├── widgets.py           # 自定义控件（RoundedCard, ModernButton, StatusPill 等）
│   │   ├── sidebar.py           # 卡片式任务侧栏
│   │   └── library_view.py      # 三栏文献书架（列表+详情+元数据）
│   ├── core/
│   │   ├── __init__.py          # 模块统一导出
│   │   ├── abstract.py          # 六级摘要补全流水线（并行版）
│   │   ├── code_protector.py    # 底层代码保护（MAC + 密码验证）
│   │   ├── config_manager.py    # 配置读写、输入校验、路径管理
│   │   ├── coupon_manager.py    # 礼品券管理 + 14天免费试用（多文件锚定防清理）
│   │   ├── email_sender.py      # 邮件发送（SSL 465 / TLS 587 双模式）
│   │   ├── engine.py            # 编排协调层（历史检索/增量检查/报告生成）
│   │   ├── library.py           # 文献书架数据模型（JSON 持久化）
│   │   ├── search.py            # CrossRef 检索 + ISSN 解析 + cursor 分页
│   │   └── session.py           # HTTP Session
│   ├── data/                    # JSON 持久化（任务/邮箱/许可/推送记录/调度状态）
│   ├── logo/
│   │   ├── zm.png               # 应用图标
│   │   ├── ztl.png              # 标题栏图标
│   │   ├── qdy.png              # 启动页图片
│   │   └── icons/               # PIL 生成的 24×24 线性图标 PNG（48 个）
│   └── output/
│       └── unsent/              # 邮件发送失败的附件备份
├── docs/                        # 文档目录
└── dist/                        # PyInstaller 打包输出（需本地构建）
    └── HONGXUN/
        ├── HONGXUN.exe          # 打包后的可执行文件
        └── _data/               # 运行时数据目录（自动生成）
            └── data/            # 配置/任务/许可数据
```

## 核心功能

### 论文检索
- CrossRef API，按期刊 + 时间范围检索
- **Cursor 深度分页**：突破 CrossRef 单页 1000 条限制，自动翻页
- **按月切割逐月检索**：时间范围自动按月度切割，逐月检索后合并去重
- **支持检索取消**：检索过程中可随时点击「取消」按钮中止
- 关键词过滤流程（仅历史检索）：检索 → 摘要补全 → 用补全的标题+摘要匹配关键词
- **每日推送不按关键词过滤**：检索期刊所有论文，补全摘要后全部推送
- 六级摘要补全：OpenAlex → Semantic Scholar（DOI）→ Tavily 搜索引擎
- 输出格式：DOCX / DOC / TXT / MD

### 报告生成（DOCX）
- 西文 Times New Roman + 中文宋体 SimSun，5号字（10.5pt），固定行间距 18pt
- 使用文本行格式代替表格，大幅减少 XML 体积

### 邮件推送
- 任意 SMTP（QQ邮箱/163/126/Gmail/新浪/Outlook/189 等）
- SMTP 供应商下拉菜单按邮箱类别分组，自动配置服务器地址
- **多端口自动回退**：同一供应商的多个端口依次尝试（465 → 587）
- 保存时自动校验邮箱域名与 SMTP 服务器是否匹配，自动修正
- 发件邮箱 + SMTP 授权码（可显/隐）+ 最多 5 个收件人（动态增删）
- **每日 8:00** 自动增量检查 → 合并多任务结果 → 一封邮件（每任务一个 DOCX 附件）
- **支持最多 5 个并行任务**
- **启动时立即检索近一周数据**，合并发送一封邮件
- 无论文时 GUI 弹窗提示
- 首次使用可享受 **14 天全部功能免费试用**（试用期内可直接使用邮件推送）

### 邮件发送失败处理
- 检索完成后先保存 DOCX 附件到 `output/unsent/`
- 发送失败时写入 `pending_email.json` 记录未发送文件清单
- 邮箱设置区提供「再发送」按钮：直接读取本地附件重发

### 推送记录保护
- 推送记录（`push_records.json`）在邮件成功发送后才写入
- 发送失败时的论文不会被标记为"已推送"，下次重试可正常识别

### 独立调度守护进程
- 与 GUI 进程解耦，GUI 关闭后继续运行
- PID 文件 + 停止标记实现进程间通信
- **macOS 开机自启**（launchd）
- **Windows 开机自启**（注册表 HKCU\…\Run）

### 14 天免费试用（多文件锚定防清理）
- 首次安装自动激活，试用记录绑定本机 MAC 地址
- 试用开始时间同时写入 **5 个锚定文件**（`trial_record.json`、`app_config.json`、`tasks.json`、`scheduler_state.json` 等）
- 删除单个配置文件会自动从其他文件恢复，无法重置试用期
- 试用结束后自动关闭付费功能

### 礼品券激活
- 24位编码（XX-XX-XX-XX-XX-XX），含 HMAC 防伪签名
- 设备绑定（MAC 地址），永久有效
- 会话级缓存：首次调用联网确认，同会话后续瞬时返回

### 底层代码保护
- 11 个 Python 源文件全部受保护（含 HONGXUN-LOCKED 标记）
- **本机 MAC 自动授权**（`ac:de:48:00:11:22`）
- 非本机设备需密码 `XHcxy1993.0827` 解锁

## UI 架构

```
client/
└── gui/                     # UI 组件包（v1.3.0 重构）
    ├── theme.py             # 颜色/字体/图标/smtp常量 + ttk 样式表
    ├── widgets.py           # 自定义 Canvas 控件库
    ├── sidebar.py           # 卡片式侧栏（替代 Listbox）
    └── library_view.py      # 三栏书架（替代 Treeview 单表）
```

### 颜色体系（v1.3.2 优化版）

| 角色 | 值 | 用途 |
|------|------|------|
| **primary** | `#2563EB` | 主色（Tailwind Blue-600，比 Apple Blue 更沉稳） |
| primary_hover | `#1D4ED8` | 悬停 |
| primary_active | `#1E40AF` | 按下 |
| primary_light | `#DBEAFE` | 选中/高亮背景 |
| **success** | `#16A34A` | 成功/运行中 |
| **warning** | `#D97706` | 警告 |
| **danger** | `#DC2626` | 错误/排除 |
| **bg_page** | `#FFFFFF` | 纯白页面背景 |
| **bg_card** | `#FFFFFF` | 卡片背景 |
| **sidebar_bg** | `#EAECEF` | 侧栏背景（更深，与页面拉大对比） |
| text_title | `#111827` | 标题（Gray-900） |
| text_body | `#1F2937` | 正文（Gray-800） |
| text_secondary | `#6B7280` | 次要文字（Gray-500） |
| text_hint | `#9CA3AF` | 占位符（Gray-400） |

### 字体系统（v1.3.2 调小）

| 层级 | 字号（macOS） | 字重 | 用途 |
|------|:-------------:|:----:|------|
| FONT_METRIC | 32pt | Bold | 仪表盘数字 |
| FONT_DISPLAY | 28pt | Bold | 大标题 |
| FONT_TITLE | 15pt | Bold | 页面标题 |
| FONT_HEADING | 13pt | Bold | 卡片标题 |
| FONT_BODY | 13pt | Normal | 正文 |
| FONT_LABEL | 13pt | Bold | 表单标签 |
| FONT_CAPTION | 11pt | Normal | 辅助文字 |
| FONT_MONO | 13pt | Normal | DOI/代码 |

- 平台适配：Windows 基准字号 9pt，macOS 13pt
- 响应式缩放：8~18pt 区间，上限 1.35x

### 布局架构

```
┌─ toolbar (44px, bg=#FFFFFF) ───────────────────────────┐
│  ⲎⲬ  HONGXUN · 论文发现工具          更新  说明  反馈   │
├────────────────────────────────────────────────────────┤
│ ┌─sidebar(#EAECEF)──┐ ┌─content──────────────────────┐│
│ │ 📋 监控任务      [+]│ │ Notebook                    ││
│ │ ┌────────────────┐ │ │ [📋任务设置][📚书架]        ││
│ │ │● 任务1         │ │ │ ┌────────────────────────┐ ││
│ │ │● 任务2         │ │ │ │ 内容区                 │ ││
│ │ └────────────────┘ │ │ └────────────────────────┘ ││
│ │ ○ 推送未启动       │ │                            ││
│ └────────────────────┘ └─────────────────────────────┘│
├─ progress (2px idle / 展开时活跃) ─────────────────────┤
├─ status (38px, bg=#EAECEF) ────────────────────────────┤
│ ● 就绪    状态消息...       🔒 郑州大学 v1.0.0 ⏱下次8:00│
└────────────────────────────────────────────────────────┘
```

### 文献书架三栏布局

```
┌─ toolbar ──────────────────────────────────────────────┐
│ 状态:[全部▾] 任务:[全部▾]  [搜索...]🔍 [📤导出][↻]   │
├───────────────────┬──────────────────┬──────────────────┤
│  论文卡片列表     │  详情预览        │  元数据          │
│  280px            │  (flex)          │  220px           │
│                   │                  │                  │
│  ▎标题1           │  ## 论文标题     │  📖 Nature       │
│   作者 et al.     │  作者列表        │  🔗 10.xxx/xxx  │
│   Nature          │                  │  📅 2026-07     │
│                   │  摘要全文...      │  🏷 keyword      │
│  ▎标题2           │                  │  📎 任务1        │
│   作者 et al.     │  ○ 待读  📤导出  │                  │
│   Science         │  ← 3/25 →        │                  │
├───────────────────┴──────────────────┴──────────────────┤
│  总计: 127  待读: 12  已读: 3  排除: 0                  │
└────────────────────────────────────────────────────────┘
```

## 自定义控件库

| 控件 | 说明 | 技术 |
|------|------|------|
| **RoundedCard** | 圆角矩形 + 单层阴影 + 1px 边框 | `tk.Canvas` + `create_polygon(smooth=True)` |
| **ModernButton** | 圆角按钮，hover 颜色过渡，press 模拟 scale(0.97) | `tk.Canvas` |
| **StatusPill** | 三色状态胶囊（待读/已读/排除） | `tk.Canvas` |
| **StatusPill** | 图标+文字组合，支持 PNG/PIL/emoji 回退 | `tk.Frame` |
| **SkeletonLoader** | 脉冲灰条骨架屏 | `tk.Canvas` + `after` 循环 |
| **EmptyState** | 居中空态（图标+标题+副标题） | `tk.Frame` |
| **ToggleSwitch** | iOS 风格开关，6 步滑动动画 | `tk.Canvas` |
| **PlaceholderEntry** | 统一输入框，placeholder 文字 | `tk.Entry` |

## 图标系统

- 48 个 24×24 线性图标 PNG（PIL 预渲染），存放在 `client/logo/icons/`
- 两色变体：`#6B7280`（默认）+ `#2563EB`（激活）
- 运行时的加载链：IconCache → 尝试 PNG → PIL 实时绘制 → emoji 回退
- 生成脚本：`tools/generate_icons.py`

## 键盘快捷键

| 平台 | 新建任务 | 保存任务 | 摘要弹窗关闭 | 切换论文（弹窗内） |
|------|---------|---------|:----------:|:----------------:|
| macOS | `Cmd+N` | `Cmd+S` | `Cmd+W` / `Esc` | `←` `→` |
| Windows | `Ctrl+N` | `Ctrl+S` | `Esc` | `←` `→` |

## 启动流程

### macOS
1. 双击 `HONGXUN-ZZU.app` → 自动运行 `python3 client/gui_app.py`
2. 或双击 `启动.command` → 终端运行
3. 启动后依次：激活检查 → 守护进程状态 → 试用期状态 → 推送结果轮询

### Windows（源码运行）
1. `cd client && python gui_app.py`
2. 或双击 `launch.bat`（需自行创建）

### Windows（打包后运行）
1. 在 Windows 上运行 `build_exe.bat`
2. 输出 `dist/HONGXUN/HONGXUN.exe`
3. 复制 `dist/HONGXUN/` 整文件夹到任意 Windows 电脑
4. 双击 `HONGXUN.exe` 运行，无需安装 Python

## Windows 跨平台适配

| 改动 | 文件 | 说明 |
|------|------|------|
| 高 DPI 感知 | `gui_app.py` | `SetProcessDpiAwareness(2)`，开启 Windows 高 DPI 支持 |
| ttk 主题 | `gui/theme.py` | 统一使用 `clam` 主题，按钮颜色跨平台一致 |
| 键盘快捷键 | `gui_app.py` | 同时绑定 `Cmd`（macOS）和 `Ctrl`（Windows） |
| 进程检测 | `gui_app.py` | Windows 用 `ctypes.OpenProcess` 替代 `os.kill(pid, 0)` |
| 进程终止 | `gui_app.py` | Windows 用 `TerminateProcess` 替代 `SIGTERM` |
| 开机自启 | `scheduler_daemon.py` | 注册表 HKCU\…\Run 方式 |
| 信号处理 | `scheduler_daemon.py` | 入口处用 try/except 包裹 `signal.signal()` |
| 打包模式路径 | `config_manager.py`, `scheduler_daemon.py` | 数据目录自动设为 exe 同级 `_data/` |
| tcl/tk 修复 | `build_exe.bat` | 自动检测并修复 tkinter |

## 版本历史

### v1.3.2-ZZU（当前）

**UI 体验优化：**
- **侧栏紧凑化**：宽度 240px → 200px，任务卡片高度 56px → 44px，底色改为 `sidebar_bg`
- **背景对比度提升**：页面背景 `#F8F9FA` → `#FFFFFF`（纯白），侧栏 `#F1F3F5` → `#EAECEF`（加深）
- **边框加深**：`#E5E7EB` → `#DEE0E3`，`#D4D6D9` → `#C8CCD0`
- **字体调小**：macOS 基准 14pt → 13pt，标题 16pt → 15pt；Windows 10pt → 9pt
- **Notebook Tab 样式**：选中态从蓝底白字改为浅蓝底深蓝字（`#DBEAFE`/`#1D4ED8`）
- **RoundedCard 阴影简化**：3 层阴影 → 单层阴影 + 1px 边框，hover 抬升动画移除
- **一键检索**：自动保存到 `output/` 目录（不再弹出保存对话框），完成后自动切换到书架
- **macOS 原生通知**：检索完成等场景使用系统通知替代自绘 Toast
- **首次运行向导**：检测到无任务时弹出 3 步引导界面
- **Logger 系统**：新增 `logging`，28 处 `except:pass` 替换为 `logger.warning(exc_info=True)`
- **硬编码 SMTP 凭据集中管理**：反馈功能凭据移至模块顶部常量

### v1.3.1-ZZU

**Bug 修复：**
- **字体变量 None 传播**：`from gui.theme import FONT_BODY` 在模块加载时捕获 `None`，`init_fonts()` 只改 theme 模块内的值，其他模块的局部变量仍为 `None`。在 `init_fonts()` 末尾通过 `sys.modules` 推送到所有依赖模块修复。
- **`_add_receiver_widget()` 方法丢失**：清理旧库代码时误删了收件邮箱控件创建方法，导致 `_load_email_config()` 崩溃。从 git 历史恢复。
- 应用启动无报错，所有功能可用。

### v1.3.0-ZZU

**GUI 架构重构：**
- 将 4348 行 `gui_app.py` 拆分为 `gui/` 组件包（5 个模块，2072 行）
- `gui/theme.py`：颜色/字体/图标/smtp 常量统一管理
- `gui/widgets.py`：自定义 Canvas 控件库（RoundedCard, ModernButton, StatusPill 等）
- `gui/sidebar.py`：卡片式侧栏（替代 Listbox）
- `gui/library_view.py`：三栏文献书架（替代 Treeview 单表）
- `gui_app.py` 缩减至 3000+ 行

**视觉全面升级：**
- **圆角 + 阴影卡片系统**：Canvas 绘制 RoundedCard（12px 圆角 + 3 层阴影 + hover 抬升动画）
- **暖色基调**：页面背景 `#F8F9FA`（原纯白）、Tailwind Blue-600 主色 `#2563EB`（原 Apple Blue）
- **语义色扩充**：从 25 个颜色键增至 45+，含 pill/task_accent/shadow 系列
- **圆角系统化**：RoundedCard 12px、ModernButton 8px、StatusPill 全圆角
- **排版层次**：9 个 FONT 常量，标题/正文/辅助文字颜色对比梯度（Gray-900/800/500/400）
- **侧栏任务卡片**：彩色边条（5 色循环）+ 任务名 + 状态指示，替代单行 Listbox
- **文献书架三栏布局**：左列表（PaperCard 卡片） + 中详情预览（QuickLookPanel） + 右元数据（MetadataCard）
- **Quick Look**：空格键展开/收起 inline 摘要预览，Escape 关闭
- **批量操作**：Ctrl/Shift 多选 + 批量改状态（待读/已读） + 批量导出
- **48 个线性图标 PNG**：PIL 预渲染，两色变体，emoji 降级回退

**微交互：**
- Toast 滑入动画（从下方 30px 滑入，150ms）
- 按钮 hover 颜色过渡（6 步 180ms `lerp_color`）
- 按钮 press 模拟 scale(0.97) 反馈
- RoundedCard hover 阴影抬升（2px，6 步 180ms）
- 骨架屏（SkeletonLoader 脉冲灰条，800ms 循环）
- 空态引导（EmptyState 居中图标 + 文字）

**文献书架功能：**
- 三栏布局替代旧 Treeview
- PaperCard 卡片列表：状态色条 + 标题 + 作者 + 期刊
- QuickLookPanel：内联摘要预览，前后导航
- MetadataCard：期刊、DOI（点击复制）、日期、关键词 pill
- Ctrl/Shift 多选 + 批量操作栏
- 空格键 Quick Look 展开/收起

### v1.2.0-ZZU

**文献书架功能：**
- 新增文献书架 Tab，自动收录每次检索结果
- 书架列表：状态（待读/已读/排除）、标题完整显示、摘要预览 120 字符、作者
- 隐藏列：期刊、DOI、发表时间、关键词、来源任务（可随时切换显示）
- 点击状态列循环切换阅读状态（待读→已读→排除）
- 点击行弹出摘要详情弹窗（前置、可选中复制、Ctrl+W 关闭）
- 弹窗内支持 ← → 箭头切换上一篇/下一篇论文
- 弹窗内元数据卡片化展示（期刊/作者/DOI/日期/关键词）
- 弹窗内可直接切换阅读状态，点击 DOI 可复制
- 书架状态筛选（全部/待读/已读/排除）+ 来源任务筛选
- 书架标题搜索（Enter 触发 🔍 按钮）
- 书架空状态引导提示
- 书架底部统计栏（总计/已读/待读/排除）
- 检索结果自动去重入库（按 DOI / title+journal 去重，跨所有历史任务）
- 导出 RIS 格式，可选择导出范围（全部/待读/已读/当前筛选）→ 供 Zotero 导入

**GUI 视觉重构（v1.2 版 Apple 色系）：**
- 颜色体系全面升级为 Apple 色系（`#007AFF`、`#34C759`、`#FF3B30`、`#F5F5F7` 等）
- 顶部工具栏精简重构（高度 48→44px）
- 左侧面板改为侧栏浅灰底 + 标题分隔线 + 底部推送状态卡片
- Notebook 标签自定义样式（选中 Apple 蓝底白字 / 未选中浅灰底）
- 进度条常驻化（不活跃时 2px 灰色细线，活跃时自动展开）
- 状态栏优化（侧栏灰底、加版号圆点指示器、代码锁移入状态栏）
- Treeview 行高 32→38，交替行色（白/浅灰）

**Bug 修复：**
- 代码锁按钮重复创建（状态栏 + links_frame 各一份）
- `_apply_lib_tags` 递归保护
- `_progress_idle` pack 时序（延迟到 status_frame 构建后）
- 激活状态显示混淆（试用期内显示"试用中"而非"已激活"）

**功能新增：**
- 检索取消功能（进度条旁的「取消」按钮）
- 多文件锚定试用（5 个配置文件，删除单个可自动恢复）

### v1.1.1-ZZU

**改进：**
- Windows 平台完整支持（进程管理、开机自启、快捷键）
- PyInstaller 打包支持（`HONGXUN.spec`、`build_exe.bat`）

### v1.1.0-ZZU（2026-07-21）

**修复：**
- 核心 Bug：试用期内邮件发送失败（`is_activated()` → `is_feature_allowed()`）

### v1.0.0-ZZU（郑州大学定制版）

**新增功能：**
- MAC 绑定的 14 天免费试用
- 邮件发送失败自动保存附件，支持再发送
- 独立调度守护进程 v2.0

## 依赖

```bash
pip install requests python-docx Pillow
```
