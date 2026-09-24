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
4. Site Log／网站日志
5. Daily News／每日新闻
6. Opportunities／资讯
7. 中／EN 分段式语言切换

语言切换必须进入当前页面对应的译文。每组双语页面通过 Front Matter 中的 `lang` 和 `translation_url` 对应。

主要页面：

- `_pages/about.md`、`_pages/about-zh.md`：首页。
- `_pages/publications.html`、`_pages/publications-zh.html`：著作和期刊论文。
- `_pages/year-archive.html`、`_pages/study-notes-zh.html`：研究方法、智能传播、全球传播三类札记。
- `_pages/site-log.html`、`_pages/site-log-zh.html`：网站修改记录。
- `_pages/daily-news.html`、`_pages/daily-news-zh.html`：按日期归档的新闻简讯。
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

每次拥有者向 `master` 推送网页修改后，工作流会记录日期、修改类别、提交说明和提交链接。自动新闻提交、日志机器人提交和合并噪声不会写入日志。同一提交重复运行不会产生重复记录，最多保留最近 100 条。

### 描述文字的硬性要求（每次改动日志相关代码都必须遵守）

一句话，**具体**，简短。必须写成下面两种句式之一：

- `增加了X，该功能用于X` —— X 是站内具体的页面、板块、控件或脚本；
- `对X进行了X改动，使X变得X` —— 说明改动对象和改动带来的结果。

禁止使用"体验""效果""内容""质量"这类空泛名词，也禁止"更清楚、更顺手""持续改进""进一步完善""优化体验""界面更友好"这类套话。英文条目同样一句话镜像表达（Added X, which does Y. / Changed X so that Y.），至多 22 个单词。

描述文字由 GitHub Models（`openai/gpt-4o-mini`，工作流已授予 `models: read`）按上述规则生成，脚本会先校验：命中禁用词、超长或为空的结果一律丢弃并改用回退句（回退句同样按文件类别点名具体改动对象）。模型最多重试两次。本地预演：`python scripts/update_site_log.py --only-shas <sha1,sha2> --dry-run`（需 `GITHUB_TOKEN`）。注意：本工作区的沙箱网络无法真正访问 `models.github.ai`（请求会被拦截返回空响应），模型效果只能在 GitHub Actions 中验证。

页面只读取已经保存的数据，不再依赖访客浏览器实时请求 GitHub API。需要手动补充时，可编辑 `_data/site_updates.json`，但应保持现有字段结构，并遵循上面的句式要求。

## 10. 每日新闻自动化

- 数据文件：`_data/daily_news.json`
- 抓取脚本：`scripts/fetch_daily_news.py`
- 自动任务：`.github/workflows/daily-news.yml`
- 首页组件：`_includes/daily-news-widget.html`

工作流每小时从公开 RSS 新闻源整理标题，按上海时区日期保存。数据结构为：

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

最多保存 90 天，每天最多 9 条。任务会在写入前同步最新分支，推送竞争时最多自动重试三次。新闻标题和链接归原发布机构所有，网站只做索引。

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
- `git diff --check` 无错误。
- 工作区无测试缓存、临时文件或私人简历。
- 明确告知用户是否仍需点击 `Push origin`。

## 13. 资讯页自动化

- 数据文件：`_data/opportunities.json`
- 抓取脚本：`scripts/fetch_opportunities.py`
- 自动任务：`.github/workflows/opportunities.yml`
- 页面：`_pages/opportunities.html`、`_pages/opportunities-zh.html`

任务每天从官方信息源收集两个板块，按上海时区日期去重后追加保存，最多保留 180 天：

1. 实习资讯：页面内再分为"联合国实习"与"企业实习"两个子板块（条目带 `group` 字段：`un` / `company`）。来源为联合国（UNICEF、UN Women）与知名外企（Amazon、Airbnb、Stripe、Anthropic、Cloudflare）的官方招聘接口，仅保留标题含 "intern" 的职位。
2. 院校资讯：QS 前 50 高校新闻传播院系官方页面（牛津 RISJ、剑桥 POLIS、哈佛 Shorenstein、NYU、斯坦福、USC Annenberg、香港大学 JMSC、威斯康星麦迪逊、南洋理工 WKWSCI），提取含 visiting、exchange、joint、fellowship、studentship 等关键词的条目。

某天没有新信息时，脚本不修改数据文件，工作流检测到无差异即跳过提交。已收录的条目按 URL 去重，不会重复出现。新增信息源时编辑脚本顶部的 `INTERN_SOURCES` / `ACADEMIA_SOURCES` 列表即可。

### 归档只增不改（改动前必读）

采集结果**只追加、不覆盖**：新条目写入当天日期的 `items`，已有日期合并而非重建，脚本每次运行前会先归一化归档（同一日期合并为一条、日内按 URL/标题去重、无日期的条目丢弃），最多保留 180 天。切勿改成"每天生成一份新数据覆盖写入"。

页面呈现与存储配套：**每一天是一个 `<details>`**（`class="daily-news-day opps-day"`，带 `data-filter-date` 以便日期筛选器生效），**最新一天默认 `open`，更早的收起**；`_includes/opps-archive-controls.html` 提供"展开/收起全部日期"按钮。这样归档可以持续增长而不会把最新内容埋进长列表。相关样式在 `_sass/_content-refinements.scss` 的 `.opps-day` / `.opps-toolbar` 段。

## 14. 当前迁移注意事项

换电脑前必须确保旧电脑上的本地提交全部推送。只有出现在 GitHub 仓库中的内容，才能在新电脑克隆后完整恢复。Codex 对话记录不会随仓库迁移，但本文件和 `AGENTS.md` 已保存足够的项目背景。
