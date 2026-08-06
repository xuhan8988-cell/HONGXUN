# HONGXUN — Academic Paper Monitor & Literature Manager

A cross-platform desktop application for monitoring academic papers, enriching abstracts, AI-powered translation (multi-provider LLM), PDF download, reference formatting, and daily email push notifications.

## Features

- **Paper Monitoring** — Search CrossRef by journal + keywords, automatic weekly segmentation for complete results
- **Smart Journal Picker** — Built-in 4,295 journal database with a 3-level category tree (大类→小类→分区), search, multi-select, favorites, detail view, and batch import
- **6-Tier Abstract Enrichment** — OpenAlex → Semantic Scholar → PubMed → Tavily web search
- **AI Translation** — Multi-provider LLM (English → Chinese): **DeepSeek / Qwen / Zhipu GLM / Doubao / Kimi / MiniMax**, key configured via a settings dialog with connection testing
- **Reference Format Assistant** — Convert reference lists to 6 standard styles (GB/T 7714, IEEE, APA 7th, Chicago, MLA, Harvard), with cross-reference hyperlinks, superscript citations, reordering, and AI-driven custom-format parsing (upload journal requirements)
- **PDF Download** — Multi-source fallback (Unpaywall → OpenAlex → arXiv → PMC → publisher), optional Sci-Hub enhancement
- **Structured Reports** — Generate DOCX reports with formatted metadata, abstracts, and bilingual (EN+CN) content
- **Daily Email Push** — Scheduled incremental check with SMTP email delivery, multi-recipient support, configurable push time
- **Literature Bookshelf** — 3-pane library manager: paper list, QuickLook preview, metadata card; batch operations, RIS export
- **Account & Login** — Email + password registration (verification code via SMTP), encrypted password storage (PBKDF2), session-based login; guest mode can browse but not execute
- **Paid Subscription** — 3 tiers (month / year / lifetime) via QR-code payment, with coupon activation coexisting
- **Invitation Codes** — Users generate unique 8-char invite codes; inviting a friend grants 1 month of full features
- **Unified Access Control** — Free tier after login (search / bookshelf / GB/T formatting); advanced features gated by subscription
- **Auto Update** — GitHub Release-based update mechanism with one-click upgrade

## Subscription Plans

| Plan | Price | Validity |
|------|:-----:|:--------:|
| 1 month | ¥9.9 | 30 days |
| 1 year | ¥99 | 365 days |
| Lifetime | ¥299 | Permanent |

Payment uses QR-code scanning via an aggregator (个人开发者免签约). The payment adapter interface is stubbed in `client/core/subscription.py` — replace `create_order`/`query_order` to integrate a real platform.

## Account System

- **Registration**: email + verification code (sent via built-in SMTP) + password (≥6 chars, letters & digits); same email registers once
- **Login**: email + password, session persisted locally
- **Guest mode**: can view the interface but cannot execute any feature
- **Invitation**: generate a unique 8-char invite code; friends who register with it grant you 1 month of full features

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`

## Quick Start

```bash
pip install -r requirements.txt

python client/gui_app.py
```

For AI translation, open **设置 → AI 翻译 → 配置 API**, select a provider, enter your API key, and click **测试连接**.

## Platform Support

- macOS (Intel & Apple Silicon)
- Windows 10/11
- Linux (experimental)

## Tech Stack

- **GUI**: Python + Tkinter (ttk themed)
- **Search**: CrossRef API (cursor-based deep pagination)
- **Abstract**: OpenAlex, Semantic Scholar, PubMed, Tavily
- **Translation**: OpenAI-compatible LLM APIs (DeepSeek, Qwen, Zhipu, Doubao, Kimi, MiniMax)
- **Formatting**: python-docx + raw OOXML (bookmarks, internal hyperlinks, superscript)
- **Email**: SMTP SSL (QQ, 163, Gmail, Outlook, etc.)
- **Auth**: PBKDF2 password hashing + coupon HMAC-SHA256 + subscription expiry

## Project Structure

```
client/
├── gui_app.py              # Main application entry
├── scheduler_daemon.py     # Daily push scheduler daemon
├── core/
│   ├── engine.py           # Orchestration layer (search → enrich → translate → report)
│   ├── search.py           # CrossRef search with ISSN resolution
│   ├── abstract.py         # 6-tier abstract enrichment pipeline
│   ├── translator.py       # Multi-provider LLM translation
│   ├── subscription.py     # Paid subscription (3 tiers, QR payment adapter) [locked]
│   ├── coupon_manager.py   # Coupon generation, validation, redemption + access control
│   ├── user_manager.py     # Email/password registration, login, session, invite codes
│   ├── ref_formatter/      # Reference formatting engine (6 styles + AI custom parse)
│   │   ├── engine.py       # Unified entry
│   │   ├── parser.py       # Document parsing (citations, references)
│   │   ├── formatter.py    # Format conversion
│   │   ├── cross_ref.py    # Cross-reference hyperlinks
│   │   ├── reorder.py      # Reorder by first appearance
│   │   ├── validator.py    # Format validation
│   │   ├── llm_enhancer.py # AI custom-format parsing
│   │   └── formats/        # GB/T 7714, IEEE, APA 7th, Chicago, MLA, Harvard
│   ├── journal_store.py    # Journal database (SQLite, seeded from journals_seed.json)
│   ├── journal_db.py       # Journal DB queries
│   ├── pdf_fetcher.py      # Multi-source PDF download
│   ├── pdf_config.py       # PDF download config
│   ├── library.py          # Literature bookshelf (JSON storage)
│   ├── email_sender.py     # SMTP email sending + verification codes
│   ├── config_manager.py   # Config read/write, validation
│   ├── session.py          # Shared HTTP session
│   ├── auto_updater.py     # Auto update mechanism (GitHub Releases)
│   └── code_protector.py   # Source code integrity protection
├── gui/
│   ├── theme.py            # Colors, fonts, icons, design tokens, ttk styles
│   ├── widgets.py          # Custom widgets (Card, Switch, Scrollbar, IconButton, Toast, etc.)
│   ├── sidebar.py          # Task sidebar + page navigation
│   ├── dashboard.py        # Home dashboard (stats, recent papers, task status)
│   ├── library_view.py     # 3-pane library view
│   ├── ref_formatter_view.py # Reference format assistant UI (with AI parse flow)
│   ├── journal_picker.py   # Journal picker (category tree + search)
│   ├── journal_detail.py   # Journal detail dialog
│   └── journal_import.py   # Journal batch import
└── logo/                   # Application icons
```

## Access Control

After login, free-tier features are available (search, bookshelf up to 50 papers, GB/T 7714 formatting). Advanced features (AI translation, all formats, custom AI parsing, email push) require a paid subscription. Guests can browse the interface but cannot execute any feature.

## License

MIT License — see [LICENSE](LICENSE) for details.
