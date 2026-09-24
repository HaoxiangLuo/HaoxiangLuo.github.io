# Agent Guidelines for Academic Pages (academicpages.github.io, v.0.9.x)

**This file contains important information for coding agents working in this repo.**

`academicpages.github.io` is a Jekyll theme for academic, professional, and personal portfolio-oriented websites. The the typical use pattern is to "Use this template" to "Create a new repository" (see [Creating a repository from a template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)) where the user will then make their own edits to customize the template to create their own personal GitHub pages website. 

If a user has created a personal website, there is **no need** to create a pull request back to the `academicpages.github.io` repository.

## Project-specific instructions for HaoxiangLuo.github.io

This repository is Haoxiang Luo's bilingual academic website, published from the `master` branch at <https://haoxiangluo.github.io/>. Before making changes, read `CODEX_HANDOFF.md` in full and inspect `git status -sb` so that automated news commits are synchronized before editing.

- Preserve the established Apple-inspired visual system: graphite, white, warm gray, restrained system blue, generous spacing, precise typography, subtle borders and shadows. Do not copy Apple assets or marketing layouts literally.
- Keep desktop and phone behavior separate. Desktop-only refinements belong in `@media (min-width: 1024px)`; phone fixes belong in `@media (max-width: 767px)`. Verify both after layout work.
- Maintain paired English and Chinese pages and their `translation_url` values. The segmented language control must link to the corresponding page, not merely change its appearance.
- The profile panel appears only on the home page. Keep the personalized location text `Earth`. Email remains in the profile panel.
- Public navigation consists of Home, Publications, Study Notes, Site Log, Daily News, Opportunities, and the language selector.
- Do not publish the private CV, fund projects, Chinese conference records, or Jiangxi Normal University journal-work experience. Education shows only the doctoral stage. Conference content is limited to ICA and AMIC. Monographs and academic service may be public.
- Use publication labels exactly where applicable: `SSCI Q1`, `EI（JA）`, `CSSCI`, `CSSCI扩展`, and `AMI`. Ordinary journals receive no badge.
- `_data/daily_news.json`, `_data/opportunities.json`, and `_data/site_updates.json` are durable generated archives. Update their scripts/workflows rather than hand-editing their structure unless repairing data.
- Site-log entries must be concrete and short. One sentence, in one of these shapes: `增加了X，该功能用于X` or `对X进行了X改动，使X变得X`. X is a concrete part of the site (a page, a section, a control, a script), never a vague noun such as 体验/效果/内容. Banned: 更清楚、更顺手、持续改进、进一步完善、优化体验、界面更友好. English mirrors it in one sentence. Hand-written entries in `_data/site_updates.json` follow the same rule.
- Opportunities content is additive, never replaced: each run files new items under their own date in `_data/opportunities.json` (deduped by URL/title, one entry per date, newest first). On the page each day is a `<details>` — the newest day starts open and earlier days are folded closed, so the archive can grow without burying the latest entries.
- Never discard unrelated local changes. Do not reset the repository or overwrite generated archives when resolving an automation race.
- Finish meaningful work with proportional checks, a concise commit, and a clear statement of whether `Push origin` is still required.
