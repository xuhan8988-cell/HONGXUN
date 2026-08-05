"""
鸿讯 HONGXUN · 智能期刊数据库访问层
版本 1.0.0

为"智能期刊选择器"提供期刊目录查询、收藏、浏览历史与推荐。
与 journal_db.py（名称→ISSN 硬编码映射，供检索用）完全独立、并存。

数据存储：
  - 期刊目录  → client/data/journals.db（SQLite，只读目录，首次打开时从 seed 灌入）
  - 收藏      → client/data/journal_favorites.json（JSON 原子写）
  - 浏览历史  → client/data/journal_view_history.json（JSON 原子写）
"""

import json
import os
import re
import shutil
import sqlite3
import sys
import unicodedata

from . import config_manager

DATABASE_PATH = os.path.join(config_manager.DATA_DIR, "journals.db")
SEED_PATH = os.path.join(config_manager.DATA_DIR, "journals_seed.json")
FAVORITES_PATH = os.path.join(config_manager.DATA_DIR, "journal_favorites.json")
HISTORY_PATH = os.path.join(config_manager.DATA_DIR, "journal_view_history.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS journals (
    jid            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT NOT NULL UNIQUE,
    full_name_cn   TEXT,
    abbreviation   TEXT,
    issn           TEXT,
    eissn          TEXT,
    category       TEXT,
    subcategory    TEXT,
    cas_division_2024 INTEGER DEFAULT 0,
    is_top         INTEGER DEFAULT 0,
    impact_factor_2025 REAL DEFAULT 0,
    h_index        INTEGER DEFAULT 0,
    publisher      TEXT,
    country        TEXT,
    is_oa          INTEGER DEFAULT 0,
    review_cycle   TEXT,
    acceptance_rate TEXT
);
CREATE INDEX IF NOT EXISTS idx_journals_category ON journals(category);
CREATE INDEX IF NOT EXISTS idx_journals_division ON journals(cas_division_2024);
CREATE INDEX IF NOT EXISTS idx_journals_if ON journals(impact_factor_2025);
CREATE INDEX IF NOT EXISTS idx_journals_top ON journals(is_top);
CREATE INDEX IF NOT EXISTS idx_journals_issn ON journals(issn);

-- 期刊-小类关联表（多对多：一本期刊可属多个「大类→小类」节点）
CREATE TABLE IF NOT EXISTS journal_subcats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    jid        INTEGER NOT NULL,
    category   TEXT,
    subcat     TEXT,
    division   INTEGER DEFAULT 0,
    FOREIGN KEY (jid) REFERENCES journals(jid)
);
CREATE INDEX IF NOT EXISTS idx_subcats_cat ON journal_subcats(category);
CREATE INDEX IF NOT EXISTS idx_subcats_node ON journal_subcats(category, subcat, division);
CREATE INDEX IF NOT EXISTS idx_subcats_jid ON journal_subcats(jid);
"""

# 当前 seed 数据结构版本（用于 db 重建检测）
SEED_VERSION = 2

# 排序白名单：{排序键: (SQL 列, 方向)}
_SORT_MAP = {
    "if_desc": ("impact_factor_2025", "DESC"),
    "if_asc": ("impact_factor_2025", "ASC"),
    "name_asc": ("full_name", "ASC"),
    "division_asc": ("cas_division_2024", "ASC"),
}

# 中科院分区标签
DIVISION_LABELS = {1: "1区", 2: "2区", 3: "3区", 4: "4区"}


def _norm(name: str) -> str:
    """期刊名归一化，用于模糊匹配。"""
    n = unicodedata.normalize("NFKC", (name or "").lower())
    n = n.replace("&", "and")
    n = re.sub(r"[.,;:()\[\]\"\\'\-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.startswith("the "):
        n = n[4:]
    return n


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    tmp = path + ".tmp." + str(os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


class JournalStore:
    """智能期刊数据库访问层。"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH
        self._favorites = None
        self._history = None

    # ── 数据库初始化 ──────────────────────────────────────
    @staticmethod
    def _ensure_packaged_seed() -> None:
        """打包模式下把 seed 文件从 PyInstaller 解包目录复制到数据目录。

        PyInstaller 通过 spec 的 datas 把 journals_seed.json 打包进 _MEIPASS，
        而运行时数据目录在 exe 同级 _data/data/。首次启动时若数据目录缺失
        seed 文件，则从 _MEIPASS 复制过去，保证期刊选择器可用。
        """
        if not getattr(sys, "frozen", False):
            return
        if os.path.exists(SEED_PATH):
            return
        try:
            bundle = getattr(sys, "_MEIPASS", "")
            if not bundle:
                return
            src = os.path.join(bundle, "data", "journals_seed.json")
            if os.path.exists(src):
                os.makedirs(os.path.dirname(SEED_PATH), exist_ok=True)
                shutil.copy2(src, SEED_PATH)
        except Exception:
            pass

    def ensure_db(self) -> None:
        """建表；检测 schema 版本，过旧则重建；空库则从 seed 灌入。"""
        self._ensure_packaged_seed()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            old_version = conn.execute("PRAGMA user_version").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0] if self._has_table(conn, "journals") else 0

            if old_version < SEED_VERSION and count > 0:
                # 旧版本数据 → 重建（目录只读数据，重灌最干净）
                self._recreate_tables(conn)
                count = 0
            else:
                conn.executescript(_SCHEMA)

            if count == 0 and os.path.exists(SEED_PATH):
                self._seed_from_json(conn)
            conn.execute(f"PRAGMA user_version = {SEED_VERSION}")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _has_table(conn, name: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        return row is not None

    def _recreate_tables(self, conn: sqlite3.Connection) -> None:
        """DROP 旧表重建（保留 journals 主表结构，重建关联表）。"""
        conn.execute("DROP TABLE IF EXISTS journal_subcats")
        conn.execute("DROP TABLE IF EXISTS journals")
        conn.executescript(_SCHEMA)

    def _seed_from_json(self, conn: sqlite3.Connection) -> int:
        """从 seed 文件灌入期刊目录 + 小类关联，返回导入条数。"""
        try:
            with open(SEED_PATH, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"[journal_store] 读取 seed 失败: {e}", flush=True)
            return 0

        # 新版 seed 为 {seed_version, journals: [...]}；旧版为裸数组（兼容）
        if isinstance(payload, dict):
            records = payload.get("journals", [])
        else:
            records = payload

        n = 0
        for r in records:
            try:
                cur = conn.execute(
                    """
                    INSERT OR REPLACE INTO journals (
                        full_name, full_name_cn, abbreviation, issn, eissn,
                        category, subcategory, cas_division_2024, is_top,
                        impact_factor_2025, h_index, publisher, country,
                        is_oa, review_cycle, acceptance_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.get("full_name", ""),
                        r.get("full_name_cn", "") or "",
                        r.get("abbreviation", "") or "",
                        r.get("issn", "") or "",
                        r.get("eissn", "") or "",
                        r.get("category", "") or "",
                        r.get("subcategory", "") or "",
                        int(r.get("cas_division_2024", 0) or 0),
                        int(r.get("is_top", 0) or 0),
                        float(r.get("impact_factor_2025", 0) or 0),
                        int(r.get("h_index", 0) or 0),
                        r.get("publisher", "") or "",
                        r.get("country", "") or "",
                        int(r.get("is_oa", 0) or 0),
                        r.get("review_cycle", "") or "",
                        r.get("acceptance_rate", "") or "",
                    ),
                )
                jid = cur.lastrowid

                # 小类关联（多对多）。分区判定已改用期刊大类分区，
                # 因此小类分区不做过滤，保证所有期刊（含小类为3/4区者）都能在分类树中归类。
                for s in r.get("subcats", []) or []:
                    conn.execute(
                        "INSERT INTO journal_subcats (jid, category, subcat, division) VALUES (?, ?, ?, ?)",
                        (jid, s.get("category", "") or r.get("category", ""),
                         s.get("subcat", "") or "", int(s.get("division", 0) or 0)),
                    )
                n += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
        return n

    def count(self) -> int:
        try:
            conn = sqlite3.connect(self.db_path)
            n = conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
            conn.close()
            return n
        except Exception:
            return 0

    # ── 查询 ─────────────────────────────────────────────
    def query(self, keyword: str = None, category: str = None,
              division: int = None, only_top: bool = None, only_oa: bool = None,
              if_min: float = None, sort: str = "if_desc",
              limit: int = 50, offset: int = 0) -> list[dict]:
        """多条件筛选期刊，返回当前页字典列表。sort 取 _SORT_MAP 白名单。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = "SELECT * FROM journals WHERE 1=1"
            params = []
            if keyword:
                kw = _norm(keyword)
                sql += (" AND (full_name LIKE ? OR full_name_cn LIKE ?"
                        " OR abbreviation LIKE ? OR issn LIKE ? OR category LIKE ?)")
                p = f"%{kw}%"
                params.extend([p, p, p, p, p])
            if category:
                sql += " AND category = ?"
                params.append(category)
            if division:
                sql += " AND cas_division_2024 = ?"
                params.append(int(division))
            if only_top:
                sql += " AND is_top = 1"
            if only_oa:
                sql += " AND is_oa = 1"
            if if_min is not None:
                sql += " AND impact_factor_2025 >= ?"
                params.append(float(if_min))

            col, direction = _SORT_MAP.get(sort, _SORT_MAP["if_desc"])
            sql += f" ORDER BY {col} {direction}, full_name ASC"
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])

            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def count_filtered(self, keyword: str = None, category: str = None,
                       division: int = None, only_top: bool = None,
                       only_oa: bool = None, if_min: float = None) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            sql = "SELECT COUNT(*) FROM journals WHERE 1=1"
            params = []
            if keyword:
                kw = _norm(keyword)
                sql += (" AND (full_name LIKE ? OR full_name_cn LIKE ?"
                        " OR abbreviation LIKE ? OR issn LIKE ? OR category LIKE ?)")
                p = f"%{kw}%"
                params.extend([p, p, p, p, p])
            if category:
                sql += " AND category = ?"
                params.append(category)
            if division:
                sql += " AND cas_division_2024 = ?"
                params.append(int(division))
            if only_top:
                sql += " AND is_top = 1"
            if only_oa:
                sql += " AND is_oa = 1"
            if if_min is not None:
                sql += " AND impact_factor_2025 >= ?"
                params.append(float(if_min))
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def get_by_id(self, jid: int) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            r = conn.execute("SELECT * FROM journals WHERE jid = ?", (jid,)).fetchone()
            return self._row_to_dict(r) if r else None
        finally:
            conn.close()

    def get_by_name(self, name: str, fuzzy: bool = True) -> dict | None:
        """按名称查期刊。精确优先，模糊（containment）兜底。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            r = conn.execute("SELECT * FROM journals WHERE full_name = ?",
                             (name,)).fetchone()
            if r:
                return self._row_to_dict(r)
            r = conn.execute("SELECT * FROM journals WHERE abbreviation = ?",
                             (name,)).fetchone()
            if r:
                return self._row_to_dict(r)
            r = conn.execute("SELECT * FROM journals WHERE issn = ?",
                             (name,)).fetchone()
            if r:
                return self._row_to_dict(r)
            if fuzzy:
                n = _norm(name)
                if n:
                    for row in conn.execute(
                            "SELECT * FROM journals ORDER BY impact_factor_2025 DESC"):
                        d = self._row_to_dict(row)
                        if n == _norm(d["full_name"]):
                            return d
                    # containment 匹配
                    for row in conn.execute(
                            "SELECT * FROM journals WHERE full_name LIKE ? ORDER BY impact_factor_2025 DESC",
                            (f"%{n}%",)):
                        return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def distinct_categories(self) -> list[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT category FROM journals WHERE category != '' "
                "ORDER BY category").fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    # ── 三级分类树（大类 → 小类 → 分区） ─────────────────
    def get_category_tree(self) -> list[dict]:
        """返回三级分类树：大类节点带小类，小类节点带分区数量。

        [{name, count, children: [{name, count, children: [{name(分区), count, division}]}]}]
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # 统计每个「大类-小类-分区」的期刊数。
            # 分区一律以期刊的大类分区（j.cas_division_2024）为准，忽略小类分区。
            rows = conn.execute(
                """
                SELECT s.category, s.subcat, j.cas_division_2024 AS division,
                       COUNT(DISTINCT s.jid) as cnt
                FROM journal_subcats s
                JOIN journals j ON j.jid = s.jid
                WHERE s.category != '' AND s.subcat != '' AND j.cas_division_2024 IN (1, 2)
                GROUP BY s.category, s.subcat, j.cas_division_2024
                """).fetchall()

            # 大类 → 小类 → 分区 聚合
            cat_map = {}
            for category, subcat, division, cnt in rows:
                if division not in (1, 2):
                    continue
                cat_node = cat_map.setdefault(category, {"name": category, "count": 0, "children": []})
                cat_node["count"] += cnt
                sub_node = None
                for c in cat_node["children"]:
                    if c["name"] == subcat:
                        sub_node = c
                        break
                if sub_node is None:
                    sub_node = {"name": subcat, "count": 0, "children": []}
                    cat_node["children"].append(sub_node)
                sub_node["count"] += cnt
                div_name = DIVISION_LABELS.get(division, f"{division}区")
                sub_node["children"].append({"name": div_name, "count": cnt, "division": division})

            # 排序（大类按拼音/名称，子类按数量降序，分区按编号）
            result = []
            for cat in sorted(cat_map.values(), key=lambda x: x["name"]):
                cat["children"].sort(key=lambda x: (-x["count"], x["name"]))
                for sub in cat["children"]:
                    sub["children"].sort(key=lambda x: (x.get("division") or 99))
                result.append(cat)
            return result
        finally:
            conn.close()

    def get_category_path(self, category: str, subcat: str, division: int) -> list[str]:
        """获取面包屑路径 [大类, 小类, 分区]。"""
        return [category, subcat, DIVISION_LABELS.get(division, f"{division}区")]

    def get_journals_by_node(self, category: str, subcat: str = None, division: int = None,
                             sort: str = "if_desc", limit: int = 500, offset: int = 0) -> list[dict]:
        """按「大类→小类→分区」节点查询期刊。subcat/division 可选逐级收窄。
        分区以期刊大类分区（cas_division_2024）为准。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = ("SELECT DISTINCT j.* FROM journals j "
                   "JOIN journal_subcats s ON j.jid = s.jid "
                   "WHERE j.cas_division_2024 IN (1, 2)")
            params = []
            if category:
                sql += " AND s.category = ?"
                params.append(category)
            if subcat:
                sql += " AND s.subcat = ?"
                params.append(subcat)
            if division:
                sql += " AND j.cas_division_2024 = ?"
                params.append(int(division))
            col, direction = _SORT_MAP.get(sort, _SORT_MAP["if_desc"])
            sql += f" ORDER BY j.{col} {direction}, j.full_name ASC"
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def count_by_node(self, category: str, subcat: str = None, division: int = None) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            sql = ("SELECT COUNT(DISTINCT j.jid) FROM journals j "
                   "JOIN journal_subcats s ON j.jid = s.jid "
                   "WHERE j.cas_division_2024 IN (1, 2)")
            params = []
            if category:
                sql += " AND s.category = ?"
                params.append(category)
            if subcat:
                sql += " AND s.subcat = ?"
                params.append(subcat)
            if division:
                sql += " AND j.cas_division_2024 = ?"
                params.append(int(division))
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def search_journals(self, keyword: str, sort: str = "if_desc", limit: int = 100) -> list[dict]:
        """按名称/ISSN 搜索期刊（分类树搜索用）。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            kw = _norm(keyword or "")
            if not kw:
                return []
            p = f"%{kw}%"
            col, direction = _SORT_MAP.get(sort, _SORT_MAP["if_desc"])
            rows = conn.execute(
                f"SELECT * FROM journals WHERE full_name LIKE ? OR full_name_cn LIKE ? "
                f"OR abbreviation LIKE ? OR issn LIKE ? "
                f"ORDER BY {col} {direction} LIMIT ?",
                (p, p, p, p, int(limit))).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_ids(self, jids: list) -> list[dict]:
        """按 id 列表批量取期刊（已选回填），保持传入顺序。"""
        if not jids:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            id_map = {}
            placeholders = ",".join("?" * len(jids))
            for row in conn.execute(
                    f"SELECT * FROM journals WHERE jid IN ({placeholders})",
                    list(jids)).fetchall():
                id_map[row["jid"]] = self._row_to_dict(row)
            return [id_map[j] for j in jids if j in id_map]
        finally:
            conn.close()

    def select_all_by_node(self, category: str, subcat: str = None, division: int = None) -> list[int]:
        """返回某节点下全部期刊 id（全选用）。"""
        conn = sqlite3.connect(self.db_path)
        try:
            sql = ("SELECT DISTINCT j.jid FROM journals j "
                   "JOIN journal_subcats s ON j.jid = s.jid "
                   "WHERE j.cas_division_2024 IN (1, 2)")
            params = []
            if category:
                sql += " AND s.category = ?"
                params.append(category)
            if subcat:
                sql += " AND s.subcat = ?"
                params.append(subcat)
            if division:
                sql += " AND j.cas_division_2024 = ?"
                params.append(int(division))
            return [r[0] for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        d["is_top"] = bool(d.get("is_top"))
        d["is_oa"] = bool(d.get("is_oa"))
        d["division_label"] = DIVISION_LABELS.get(d.get("cas_division_2024"), "")
        return d

    # ── 收藏（JSON） ─────────────────────────────────────
    def _load_favorites(self) -> list[int]:
        if self._favorites is None:
            self._favorites = _load_json(FAVORITES_PATH, [])
        return self._favorites

    def add_favorite(self, jid: int) -> bool:
        favs = self._load_favorites()
        if jid not in favs:
            favs.append(jid)
            _save_json(FAVORITES_PATH, favs)
            return True
        return False

    def remove_favorite(self, jid: int) -> bool:
        favs = self._load_favorites()
        if jid in favs:
            favs.remove(jid)
            _save_json(FAVORITES_PATH, favs)
            return True
        return False

    def is_favorite(self, jid: int) -> bool:
        return jid in self._load_favorites()

    def list_favorites(self) -> list[dict]:
        favs = self._load_favorites()
        if not favs:
            return []
        # 保持收藏顺序（最近在前）
        result = []
        for jid in reversed(favs):
            j = self.get_by_id(jid)
            if j:
                j["is_favorite"] = True
                result.append(j)
        return result

    # ── 浏览历史 / 推荐（JSON） ──────────────────────────
    def _load_history(self) -> list[int]:
        if self._history is None:
            self._history = _load_json(HISTORY_PATH, [])
        return self._history

    def record_view(self, jid: int) -> None:
        hist = self._load_history()
        if jid in hist:
            hist.remove(jid)
        hist.append(jid)
        # 只保留最近 500 条
        if len(hist) > 500:
            hist = hist[-500:]
        _save_json(HISTORY_PATH, hist)

    def view_history(self, limit: int = 200) -> list[int]:
        hist = self._load_history()
        return hist[-limit:][::-1]

    def recommended(self, limit: int = 8) -> list[dict]:
        """基于浏览历史的推荐：先看最近浏览期刊的学科/分区，推荐同领域高 IF 期刊。"""
        hist = self.view_history(limit=20)
        if not hist:
            return self.hot(limit)
        # 找最近浏览期刊的学科与分区
        cats = set()
        divisions = set()
        for jid in hist:
            j = self.get_by_id(jid)
            if j:
                if j["category"]:
                    cats.add(j["category"])
                if j["cas_division_2024"]:
                    divisions.add(j["cas_division_2024"])

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if cats:
                placeholders = ",".join("?" * len(cats))
                rows = conn.execute(
                    f"SELECT * FROM journals WHERE category IN ({placeholders}) "
                    "ORDER BY impact_factor_2025 DESC LIMIT ?",
                    (*cats, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM journals WHERE is_top = 1 "
                    "ORDER BY impact_factor_2025 DESC LIMIT ?",
                    (limit,)).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def hot(self, limit: int = 8) -> list[dict]:
        """热门期刊：TOP + 高 IF（冷启动兜底）。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM journals WHERE is_top = 1 "
                "ORDER BY impact_factor_2025 DESC LIMIT ?",
                (limit,)).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()
