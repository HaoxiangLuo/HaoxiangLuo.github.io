# 网站维护与 Codex 交接说明

## 1. 项目概况

- 网站地址：<https://haoxiangluo.github.io/>
- GitHub 仓库：`HaoxiangLuo/HaoxiangLuo.github.io`
- 发布分支：`master`
- 技术结构：Jekyll + Academic Pages 模板，使用 GitHub Pages 发布
- 网站语言：中文、英文双语

在新电脑上继续工作时，请先克隆仓库，再让 Codex 阅读本文件和根目录的 `AGENTS.md`。不要从压缩包或旧文件夹继续编辑，否则容易覆盖自动生成的新闻记录。

## 2. 接手后的第一步

请向 Codex 提交以下指令：

> 请先完整阅读 `AGENTS.md` 和 `CODEX_HANDOFF.md`，然后检查 Git 状态、最近提交和自动化工作流。确认本地已经与 `origin/master` 同步后，再继续修改网站。保留现有设计体系、双语结构、隐私边界和自动归档功能；不要覆盖无关修改。

开始修改前应检查：

1. `git status -sb` 是否显示与 `origin/master` 同步。
2. GitHub Desktop 是否显示 `Fetch origin`，而不是 `Push origin` 或 `Pull origin`。
3. GitHub Actions 中 `Update daily news` 和 `Record site update` 是否正常运行。
4. 网站首页、手机端、每日新闻页和网站日志页是否可以正常打开。

## 3. 设计系统

网站追求高级、学术、精致、克制的 Apple-inspired 风格，但不直接复制苹果公司的网页或资产。

- 基础色：黑、白、石墨灰、暖灰。
- 强调色：仅在链接、焦点状态、期刊标签等位置使用系统蓝。
- 形态：大圆角、细边框、轻阴影、充足留白。
- 字体层级：标题清晰有力，正文行宽适中，避免过长段落横跨页面。
- 动效：只使用轻微悬浮、焦点和展开反馈，并兼容 `prefers-reduced-motion`。
- 首页使用深色人物面板与浅色正文卡片形成对比；人物面板只出现在首页。
- 桌面端与手机端分别处理：桌面规则通常使用 `min-width: 1024px`，手机规则使用 `max-width: 767px`。

## 4. 页面和导航

导航顺序：

1. Home／首页
2. Publications／论文发表
3. Study Notes／学习札记
4. Academic Frontiers／学界前沿
5. Site Log／网站日志
6. Daily News／每日新闻
7. Opportunities／资讯
8. 中／EN 分段式语言切换

语言切换必须进入当前页面对应的译文。每组双语页面通过 Front Matter 中的 `lang` 和 `translation_url` 对应。

主要页面：

- `_pages/about.md`、`_pages/about-zh.md`：首页。
- `_pages/publications.html`、`_pages/publications-zh.html`：著作和期刊论文。
- `_pages/year-archive.html`、`_pages/study-notes-zh.html`：研究方法、智能传播、全球传播三类札记。
- `_pages/site-log.html`、`_pages/site-log-zh.html`：网站修改记录。
- `_pages/daily-news.html`、`_pages/daily-news-zh.html`：按日期归档的新闻简讯。
- `_pages/academic-frontiers.html`、`_pages/academic-frontiers-zh.html`：十本核心期刊的最新论文归档。
- `_data/navigation.yml`：导航项目。
- `_includes/masthead.html`：顶部导航和语言控件。
- `_sass/_content-refinements.scss`：当前主要页面组件和响应式样式。
- `assets/css/main.scss`：全站基础样式及历史覆盖规则。

注意：英文 Study Notes 为兼容模板历史链接，源文件仍名为 `_pages/year-archive.html`，但其正式网址是 `/study-notes/`。不要因为文件名而误删或另建重复页面。修改双语路由后运行 `python3 scripts/check_bilingual_pages.py`。

## 5. 首页内容规则

- 人物面板仅在首页呈现。
- `Earth` 是有意保留的个性化表达，不要改成城市或国家。
- 邮箱显示在左侧人物面板。
- 不恢复 `Welcome to My World` 或独立的 Contact 区块。
- 教育背景仅体现南京大学新闻传播学博士阶段。
- 研究兴趣：全球传播中的不平等；虚假信息的扩散与工具化应用。
- 新闻窗口显示当天简讯；当天数据尚未生成时显示最近一期。

## 6. 公开内容与隐私边界

可以公开：

- 博士阶段教育背景。
- 期刊论文及规范的期刊级别。
- 专著。
- 学术服务经历。
- ICA 与 AMIC 会议经历。

不得公开：

- 完整个人简历文件。
- 基金项目。
- 中文会议记录。
- 江西师范大学工作期刊的经历。
- 其他未经明确授权的个人资料。

期刊标签只使用：`SSCI Q1`、`EI（JA）`、`CSSCI`、`CSSCI扩展`、`AMI`。普通期刊不添加标签。标签在论文卡片顶部保持统一位置。

## 7. Publications 页面

- 著作与期刊论文分栏展示。
- 论文区域桌面端每行两张紧凑卡片。
- 卡片图片使用与网站色系一致、授权清晰的自然风光图片；不要随意下载有版权风险的图片。
- 显示论文完整标题、期刊名和适用的分区标签。
- 年份筛选交互位于 `assets/js/publications.js`。
- 中英文页面的结构和筛选行为应保持一致。

## 8. Study Notes 页面

- 三张栏目卡片：研究方法、智能传播、全球传播。
- 卡片可展开，并保留上传文件及添加超链接的入口。
- 内容宽度与 Publications 页面保持一致。
- 文件和链接只能由仓库拥有者通过 GitHub 提交，访客没有上传权限。

## 9. 网站日志自动化

- 数据文件：`_data/site_updates.json`
- 生成脚本：`scripts/update_site_log.py`
- 自动任务：`.github/workflows/site-log.yml`

每次拥有者向 `master` 推送网页修改后，工作流会记录日期、修改类别、提交说明和提交链接。自动新闻提交、学界前沿自动提交、资讯自动提交、日志机器人提交和合并噪声不会写入日志。同一提交重复运行不会产生重复记录，最近索引最多保留 100 条，全部历史写入 `assets/data/archive/site-updates/YYYY.jsonl`。

### 描述文字的硬性要求（每次改动日志相关代码都必须遵守）

一句话，**具体**，简短。必须写成下面两种句式之一：

- `增加了X，该功能用于X` —— X 是站内具体的页面、板块、控件或脚本；
- `对X进行了X改动，使X变得X` —— 说明改动对象和改动带来的结果。

禁止使用"体验""效果""内容""质量"这类空泛名词，也禁止"更清楚、更顺手""持续改进""进一步完善""优化体验""界面更友好"这类套话。英文条目同样一句话镜像表达（Added X, which does Y. / Changed X so that Y.），至多 22 个单词。

描述文字由配置的 OpenAI 兼容模型服务按上述规则生成（见第 16 节），脚本会先校验：命中禁用词、超长或为空的结果一律丢弃并改用回退句（回退句同样按文件类别点名具体改动对象）。模型最多重试两次。本地预演：`python scripts/update_site_log.py --only-shas <sha1,sha2> --dry-run`（需配置好模型服务）。注意：本工作区的沙箱网络无法访问外部模型端点，模型效果只能在 GitHub Actions 中验证。

页面只读取已经保存的数据，不再依赖访客浏览器实时请求 GitHub API。需要手动补充时，可编辑 `_data/site_updates.json`，但应保持现有字段结构，并遵循上面的句式要求。

## 10. 每日新闻自动化

- 数据文件：`_data/daily_news.json`
- 抓取脚本：`scripts/fetch_daily_news.py`
- 自动任务：`.github/workflows/daily-news.yml`
- 首页组件：`_includes/daily-news-widget.html`

工作流每天三次（上海时间 09:00 / 13:00 / 19:00）从公开 RSS 新闻源整理标题，按上海时区日期保存。数据先写入长期归档 `assets/data/archive/daily-news/YYYY-MM.jsonl`，再由归档生成近期索引。数据结构为：

```json
{
  "updated_at": "ISO 时间",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "items": [
        {"title": "标题", "source": "来源", "url": "链接"}
      ]
    }
  ]
}
```

近期索引最多保存 90 天，每天最多 9 条；历史按月永久保存在归档里。任务会在写入前同步最新分支，推送竞争时最多自动重试三次。新闻标题和链接归原发布机构所有，网站只做索引。

## 11. 修改与发布流程

推荐使用 GitHub Desktop：

1. 开始工作前点击 `Fetch origin`，如有更新则先 `Pull origin`。
2. 让 Codex修改并检查文件。
3. 查看 GitHub Desktop 的 Changes，确认没有无关文件。
4. 填写简洁的 Summary 并 Commit。
5. 点击 `Push origin`。
6. 在 GitHub Actions 中确认构建及自动任务成功。
7. 等待 GitHub Pages 更新后检查桌面端和手机端。

如果自动新闻在工作期间更新了远端，先拉取再合并。解决冲突时必须同时保留人工页面修改和最新新闻数据，不能直接覆盖整个 `_data/daily_news.json`。

## 12. 每次修改后的检查清单

- 中英文页面都能访问，语言开关指向对应页面。
- 导航在桌面端居中、均匀；手机端不出现横向滚动。
- 首页人物面板文字与图标对比度足够。
- 首页正文没有被人物面板强行拉高，没有异常底部留白。
- Publications 卡片在桌面端双列、手机端单列，标签位置一致。
- Site Log 能显示最新人工发布记录。
- Daily News 能按日期显示历史记录，首页能显示当天或最近一期。
- Academic Frontiers 中英文页面卡片字段一致，标题与摘要保持原文，年月筛选可用。
- Daily News、Academic Frontiers、Site Log 选中近期索引之外的年份或月份时，能显示"正在读取历史归档…"并加载出该分卷；失败时保留已有记录并给出重试按钮。
- `git diff --check` 无错误。
- 工作区无测试缓存、临时文件或私人简历。
- 明确告知用户是否仍需点击 `Push origin`。

## 13. 资讯页自动化

- 数据文件：`_data/opportunities.json`
- 抓取脚本：`scripts/fetch_opportunities.py`
- 联合国来源注册表：`scripts/un_sources.py`（20 个机构，按发布平台各写一个采集器）
- 评分与筛选规则：`scripts/opps_match.py`（100 分制，低于 60 分不入库）
- 筛选词表：`_data/opps_filters.yml`
- 卡片模板：`_includes/opps-card.html`；筛选栏：`_includes/opps-filters.html` + `assets/js/opps-filters.js`
- 自动任务：`.github/workflows/opportunities.yml`
- 页面：`_pages/opportunities.html`、`_pages/opportunities-zh.html`

任务每天从官方信息源收集两个板块，按上海时区日期去重后追加保存，最多保留 180 天：

1. 联合国机会：`un_sources.collect_all()` 抓全部机构 → `opps_match.score_opening()` 打分 → 按「匹配度降序、截止日期升序、发布时间降序」排序 → 单机构每天最多 6 条。入库门槛：类型属于实习/培训实习/研究资助/青年专业人员，或明确接受博士、研究生、早期职业研究者的咨询岗（标 `extended`，页面单列「拓展机会」）；分数 ≥ 60。财务、人力资源、工程、医疗、后勤、采购、法务等一律不收录。
2. 企业实习：Amazon、Airbnb、Stripe、Anthropic、Cloudflare 的官方招聘接口，保留标题含 "intern" 的职位。
3. 院校资讯：QS 前 50 高校新闻传播院系官方页面（牛津 RISJ、剑桥 POLIS、哈佛 Shorenstein、NYU、斯坦福、USC Annenberg、香港大学 JMSC、威斯康星麦迪逊、南洋理工 WKWSCI），提取含 visiting、exchange、joint、fellowship、studentship 等关键词的条目。

每天运行还会**刷新已收录条目的状态**（`refresh_un_items`）：重算剩余天数、`open` / `closing` / `urgent` / `status`，超过截止日期的转为 `closed`（页面移到「已截止」），连续 21 天未在机构列表中出现的也视为下架。新增机构时编辑 `un_sources.SOURCES`；改评分权重、关键词或加分规则时改 `opps_match`。

某天没有新信息且状态没有变化，脚本不修改数据文件，工作流检测到无差异即跳过提交。

### 评分模型的两个坑（改 opps_match 前必读）

- **总分必须在封顶之后计算。** `score_opening()` 会按「标题是否点名方向」给 direction / function 封顶，但封顶只改变量本身。先求和再封顶的话，封顶等于没生效——曾因此让「循环经济实习」凭描述里的零散词拿到 72 分。现在的代码先封顶、后求和。
- **长描述里的零散命中不算方向。** 几千字的招聘启事几乎必然出现 communication / research / data，机构名（International Telecommunication Union、UN Institute for Training and Research）尤其容易误判成传播岗或研究岗。三档处理：标题点名方向 → 按实际方向打分；标题没点名但描述里有强主题词 → 中间档；两者都没有 → 封顶很低，通常直接掉到 60 分以下。
- **旧条目迁移时会用标题补评分。** 评分功能上线前存的条目只有标题和摘要，没有正文，因此分数天然偏低；页面用 `item.score >= 60` 过滤，低于门槛的不会出现在主列表，但数据仍留在归档里。

### 联合国抓取的两个已知限制

- **careers.un.org 的搜索接口会整段故障**（POST 返回 504，服务端超时，非本机问题）。UN 秘书处、UNEP、UN-Habitat、UNCTAD、OHCHR 五个源都走它；第一个失败后其余当天直接跳过（`_FAILED_HOSTS`），恢复后自动重新生效。
- **UNV、世界银行、IFAD、UNAIDS 没有可机器读取的列表**（无 feed、无公开 JSON、无服务端渲染页面），因此不在注册表里。第三方聚合站只作补充且必须保留机构名与官方链接，目前未使用。

### 联合国条目字段（改动前必读）

条目除 `title` / `url` / `source` 外还带：机构代码 `org`、岗位类型 `type`、方向 `areas`、地点 `location` / `city` / `country` / `region`、工作方式 `mode`（remote / hybrid / onsite）、部门 `department`、资格 `eligibility`、时长 `duration`、津贴 `stipend`（未说明即 `unknown`，绝不推断）、截止日期 `deadline`、剩余天数 `days_left`、状态 `status`、匹配度 `score` 与档位 `tier`、匹配理由 `reasons` / `reasons_zh`。

中文摘要、标签与匹配理由由**固定模板生成**，不经过模型，因此没有配置翻译服务时中文页也是完整的；岗位标题仍保留发布方原文，等译文补齐。

### 资讯条目双语字段（改动前必读）

条目在原文之外带译文字段：`title` / `detail` 永远保留发布方原文，`title_zh` / `detail_zh` 由采集阶段的模型服务增量写入（`title_en` / `detail_en` 为将来的中文来源预留）。英文页按 `title_en → title`、`detail_en → detail` 显示，中文页按 `title_zh → title`、`detail_zh → detail` 显示，译文暂缺时回退原文。

- 翻译只在 GitHub Actions 里进行，密钥放在仓库 secret 里，不会出现在仓库文件、页面或前端脚本中（配置方式见第 16 节）。
- **没有未认证公共翻译接口作为静默兜底**：未配置模型服务或请求失败时该字段留为待翻译，下次运行继续补齐，页面临时显示原文并在说明里注明。
- 每次运行最多翻译 `--max-translations`（默认 40）个文本字段，先补历史缺失再译当天新增；同一文本一次运行只请求一次；已有译文绝不覆盖。
- `--translate-only` 只补译文不抓取，`--dry-run` 不写文件。
- Opportunities 目前**不在** `scripts/archive_data.py` 的三层归档里（那里只有每日新闻、学界前沿、网站日志），`_data/opportunities.json` 仍是唯一存储；接入归档时把 `write_archive()` 换成 `archive_data.upsert(ROOT, "opportunities", records)` 即可，记录结构无需改变。

### 归档只增不改（改动前必读）

采集结果**只追加、不覆盖**：新条目写入当天日期的 `items`，已有日期合并而非重建，脚本每次运行前会先归一化归档（同一日期合并为一条、日内按 URL/标题去重、无日期的条目丢弃），最多保留 180 天。切勿改成"每天生成一份新数据覆盖写入"。

页面呈现与存储配套：**每一天是一个 `<details>`**（`class="daily-news-day opps-day"`，带 `data-filter-date` 以便日期筛选器生效），**最新一天默认 `open`，更早的收起**；`_includes/opps-archive-controls.html` 提供"展开/收起全部日期"按钮。这样归档可以持续增长而不会把最新内容埋进长列表。相关样式在 `_sass/_content-refinements.scss` 的 `.opps-day` / `.opps-toolbar` 段。

## 14. 学界前沿自动化

- 数据文件：`_data/academic_frontiers.json`
- 期刊清单：`_data/academic_frontiers_sources.yml`
- 抓取脚本：`scripts/fetch_academic_frontiers.py`
- 自动任务：`.github/workflows/academic-frontiers.yml`
- 页面：`_pages/academic-frontiers.html`、`_pages/academic-frontiers-zh.html`

任务每周一 09:23（上海时间）通过 OpenAlex REST API 抓取清单内期刊最近 30 天的论文（`type:article`、有摘要、非撤稿），按发表日期倒序归档；每刊最多 3 条、单次最多 24 条，归档保留 180 天。以 DOI 去重（无 DOI 时用 OpenAlex 工作 ID），归档只增不覆盖，接口异常时保留现有数据。清单内没有启用期刊时，脚本不访问 OpenAlex，直接产出空归档。

硬性约定：

- 期刊清单为人工维护，**每年由维护者依据拥有授权的 JCR 数据（Communication 类 + SSCI 收录状态）核对一次**。不得把 OpenAlex、Scopus、SJR 或任何推断结果当作 JCR 分区展示；页面只显示人工核定的 `SSCI Q1`。
- 摘要由 `abstract_inverted_index` 重建后整词截取，最多 450 字符，字段名 `abstract_excerpt`，不保存完整摘要或全文。
- 标题、作者、期刊名与摘要在中英文页面一律保持原文，不使用机器翻译；只有界面文案、筛选器、说明和空状态做双语。
- 页脚须保留"元数据来自 OpenAlex、摘要仅为节选、全文归出版方"的说明。

## 15. 长期数据归档（三层）

详细设计见 `docs/data-archive.md`，这里只记改动前必须知道的三条：

1. **归档是权威，索引是投影**。`assets/data/archive/` 下的 JSONL（每日新闻按月、学界前沿与网站日志按年）只追加、按稳定 ID 更新，永不因保留期限删除；`_data/` 里的近期 JSON 永远由 `scripts/archive_data.py` 从归档生成（90 天 / 180 天 / 100 条）。手工改 `_data/` 会在下次运行时被覆盖。
2. **页面默认轻量**。Jekyll 只构建近期索引；访客选中近期索引里没有的年份或月份时，`assets/js/archive-history.js` 才用 `fetch()` 读取 `manifest.json` 并对应该分卷，逐行解析后渲染，带双语加载/失败/重试提示，分卷在内存里缓存。
3. **写入必须原子**。所有 JSON / JSONL / manifest 都先写临时文件、解析通过后再替换；不要在脚本里直接字符串追加 JSONL。

常用命令：

```sh
python scripts/archive_data.py --all              # 重建索引与 manifest（可反复运行）
python scripts/archive_data.py --dataset daily_news --dry-run
python scripts/build_data_snapshot.py --year 2026 --output-dir ./snapshot   # 手动导出年度 ZIP
python tests/test_archive_data.py                 # 归档层单元测试
```

每年 1 月 5 日 `.github/workflows/data-archive-release.yml` 会把上一自然年的分卷打包成 `haoxiangluo-data-archive-YYYY.zip`，创建 tag `data-archive-YYYY` 的 Release（已存在则安全退出）。

## 16. 模型服务配置（改动前必读）

站内所有需要模型的脚本（网站日志描述、每日新闻译文、资讯译文）都通过 **`scripts/model_client.py`** 这一个共享客户端调用 OpenAI 兼容的 `/chat/completions` 接口。

**GitHub Models 已于 2026-07-30 全线下线**（playground、模型目录、推理接口、BYOK 全部移除，`models.github.ai` 现在对任何请求都返回 `200 OK`），因此端点、密钥、模型名**不再是常量，而是配置**：

| 环境变量 | 含义 | 未设置时 |
| --- | --- | --- |
| `TRANSLATE_BASE_URL` | OpenAI 兼容服务地址，如 `https://api.groq.com/openai/v1`；缺 `/chat/completions` 时自动补齐 | 回落到已下线的 GitHub Models 地址 |
| `TRANSLATE_API_KEY` | 该服务的密钥 | 依次回落到 `GITHUB_MODELS_TOKEN`、`GITHUB_TOKEN` |
| `TRANSLATE_MODEL` | 模型 id | `gpt-4o-mini` |

工作流里读取的是仓库变量/密钥（`daily-news.yml`、`opportunities.yml`、`site-log.yml` 三个文件的相关步骤）：

```yaml
env:
  TRANSLATE_BASE_URL: ${{ vars.TRANSLATE_BASE_URL }}
  TRANSLATE_API_KEY: ${{ secrets.TRANSLATE_API_KEY }}
  TRANSLATE_MODEL: ${{ vars.TRANSLATE_MODEL }}
```

- **只设置 `GITHUB_TOKEN` 不算已配置**：旧 provider 已下线，脚本会直接跳过请求，字段留为待翻译，不会每天白跑几十次请求。
- 密钥只存在于仓库 secret，不会进入仓库文件、页面或前端脚本；页面只读已保存的数据。
- 未配置或请求失败时：资讯字段留待下次补齐（页面回退原文），日志条目使用按改动区域生成的回退句。**任何情况下都不会写入错误译文**。
- 每日新闻仍保留原有的未认证公共接口作为兜底，所以配置模型服务后质量会更好，不配置也不会中断。

测试：`python tests/test_model_client.py`（用桩替换 `urlopen`，不联网、不消耗额度）。

## 17. 当前迁移注意事项

换电脑前必须确保旧电脑上的本地提交全部推送。只有出现在 GitHub 仓库中的内容，才能在新电脑克隆后完整恢复。Codex 对话记录不会随仓库迁移，但本文件和 `AGENTS.md` 已保存足够的项目背景。
