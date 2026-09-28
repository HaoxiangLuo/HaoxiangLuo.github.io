# 数据归档架构（三层）

网站的三类自动数据——每日新闻、学界前沿、网站日志——现在分三层存放。目标是：**历史永久保留、Jekyll 构建轻、页面首次加载轻**。

```text
_data/                         ← 近期展示索引（由归档生成，Jekyll 构建时读取）
  daily_news.json                最近 90 天
  academic_frontiers.json        最近 180 天
  site_updates.json              最近 100 条

assets/data/archive/           ← 权威历史（追加式，浏览器按需读取）
  manifest.json
  daily-news/YYYY-MM.jsonl       按月分卷
  academic-frontiers/YYYY.jsonl  按年分卷
  site-updates/YYYY.jsonl        按年分卷
```

三者的关系：

1. **JSONL 归档是权威数据**。每行一个完整 JSON 对象，只能追加，或按稳定 ID 更新同一行。
2. **`_data/` 里的 JSON 是投影**，永远由归档生成；手工改它会在下一次归档运行时被覆盖。
3. **页面默认只读 `_data/`**。只有当访客主动选择近期索引里没有的年份或月份时，浏览器才用 `fetch()` 去读对应的一个 JSONL 分卷。

这样历史可以无限增长，而网站首页、构建时间和首次加载都不受影响。

## 目录与文件

| 路径 | 作用 |
| --- | --- |
| `scripts/archive_data.py` | 合并、去重、分卷写入、重建索引、重建 manifest |
| `scripts/build_data_snapshot.py` | 把某一年的分卷打包成 ZIP，供 GitHub Release 使用 |
| `scripts/fetch_daily_news.py` | 抓新闻 → 写归档 → 生成近 90 天索引 |
| `scripts/fetch_academic_frontiers.py` | 抓论文 → 写归档 → 生成近 180 天索引 |
| `scripts/update_site_log.py` | 写日志 → 写归档 → 生成近 100 条索引 |
| `assets/js/archive-history.js` | 浏览器端：读 manifest、拉分卷、逐行解析、渲染 |
| `tests/test_archive_data.py` | 归档层的单元测试 |

## 字段

### 每日新闻（`daily-news/YYYY-MM.jsonl`）

```json
{"id": "daily-news:2026-09-28", "date": "2026-09-28",
 "items": [{"title": "...", "title_zh": "...", "source": "...", "url": "..."}],
 "fetched_at": "2026-09-28T09:00:03+08:00", "schema_version": 1}
```

一行 = 一天。`title_zh` 是机器翻译标题，可能缺失；同一天重新抓取时只覆盖有值的字段，已翻译的标题不会丢。

### 学界前沿（`academic-frontiers/YYYY.jsonl`）

```json
{"id": "doi:10.1093/joc/....", "title": "...", "abstract_excerpt": "...",
 "journal": "...", "issn_l": "...", "published_at": "YYYY-MM-DD",
 "authors": ["..."], "doi_url": "...", "landing_page_url": "...",
 "source_tier": "SSCI Q1", "focus": ["..."],
 "fetched_at": "ISO-8601", "schema_version": 1}
```

`abstract_excerpt` 最多 450 字符，不保存全文。更新同一篇文章时，新数据里缺失的字段**不会**清空已保存的字段。

### 网站日志（`site-updates/YYYY.jsonl`）

```json
{"id": "commit:<完整 SHA>", "date": "YYYY-MM-DD",
 "title_zh": "...", "title_en": "...", "purpose_zh": "...", "purpose_en": "...",
 "details_zh": "...", "details_en": "...", "story_zh": "...", "story_en": "...",
 "message": "...", "sha": "<短 SHA>", "url": "https://github.com/.../commit/<完整 SHA>",
 "schema_version": 1}
```

早期记录只有短 SHA 时，ID 退化为 `commit:<短 SHA>` 并附加 `"sha_source": "short"` 标记，记录本身不会被丢弃。

## 稳定 ID 规则

| 数据集 | 稳定 ID |
| --- | --- |
| 每日新闻 | `daily-news:YYYY-MM-DD` |
| 学界前沿 | `doi:<DOI>`；无 DOI 时用 `openalex:<work id>`；两者都没有时用 `frontiers:<内容指纹>` |
| 网站日志 | `commit:<完整 SHA>`（从 `url` 中提取）；拿不到完整 SHA 时 `commit:<短 SHA>` |

同一 ID 再次出现时是**更新**，不是新增；写入前先合并字段，因此重跑多少次结果都一样（幂等）。

## 保留策略

| 层 | 每日新闻 | 学界前沿 | 网站日志 |
| --- | --- | --- | --- |
| JSONL 归档 | 永久 | 永久 | 永久 |
| `_data/` 近期索引 | 90 天 | 180 天 | 100 条 |
| 分卷粒度 | 月 | 年 | 年 |

归档**不会因为保留期限而删除**任何记录；只有近期索引会被截断。空的分卷不会被创建，manifest 里对应数据集的 `available` 为空数组。

## 常用操作

### 重建近期索引（恢复 / 校验用）

```sh
python scripts/archive_data.py --all            # 三类一起
python scripts/archive_data.py --dataset daily_news
python scripts/archive_data.py --all --dry-run  # 只看统计，不写文件
```

从 `_data/` 与已有归档合并后重新生成索引与 manifest，可以反复运行。

### 校验 SHA-256

manifest 里的 `sha256` 基于分卷文件的实际 UTF-8 字节计算：

```sh
python - <<'PY'
import hashlib, json, pathlib
root = pathlib.Path(".")
manifest = json.loads((root / "assets/data/archive/manifest.json").read_text(encoding="utf-8"))
for dataset, entry in manifest["archives"].items():
    for part in entry["available"]:
        path = root / part["url"].lstrip("/")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(("ok  " if digest == part["sha256"] else "BAD "), path, part["records"])
PY
```

年度 ZIP 里另附 `SHA256SUMS.txt`，下载后可用 `sha256sum -c SHA256SUMS.txt` 校验。

### 手动导出年度数据

```sh
python scripts/build_data_snapshot.py --year 2026 --output-dir ./snapshot
```

产出 `haoxiangluo-data-archive-2026.zip`，内含当年分卷、manifest 摘要、`SHA256SUMS.txt` 和 `README.md`。ZIP 写到 `--output-dir` 指定的目录（工作流用 runner 临时目录），不会进仓库。

每年 1 月 5 日 `.github/workflows/data-archive-release.yml` 会自动打包上一个自然年，创建 tag `data-archive-YYYY` 的 Release；tag 已存在时安全退出，绝不覆盖旧快照。

### 只补一条日志

```sh
python scripts/update_site_log.py --only-shas <短 SHA> --sha HEAD --dry-run
```

## 写入安全

- 所有 JSON / JSONL / manifest 写入都先写同目录临时文件，解析通过后再 `os.replace()` 原子替换；解析失败则删除临时文件，原文件保持原样。
- 从不盲目字符串追加 JSONL：先合并记录，再整卷重写，因此中断的任务不会留下半行数据。
- 读取时逐行解析，坏行会被计数跳过并在日志里报告，不会让整个任务崩溃。

## 自动化频率

| 任务 | 频率 |
| --- | --- |
| Update daily news | 每天 3 次：上海时间 09:00 / 13:00 / 19:00 |
| Update academic frontiers | 每周一上海时间上午 |
| Record site update | 人工页面推送后触发；自动数据提交不写日志 |
| Data archive release | 每年 1 月 5 日 |

所有会写入仓库的工作流都会先同步 `master`、只提交自己负责的文件、推送冲突最多重试 3 次，并配置 `concurrency` 避免并发互相覆盖。
