---
title: "CiteSpace: Download and Installation Notes (2026)"
excerpt: "After CiteSpace moved to a subscription model, can the free version still be installed, and from where? A survey of channels, version expiry dates, and setup tips."
date: 2026-09-19
permalink: /posts/2026/09/citespace-download-and-install-en/
lang: en
translation_url: /posts/2026/09/citespace-download-and-install/
categories:
  - Research Methods
tags:
  - research methods
  - bibliometrics
  - CiteSpace
  - science mapping
---

While preparing a literature review, I had to set up CiteSpace again. These notes record the download channels, version expiry dates, and installation tips as of September 2026.

## 1. Current status: subscription only

The official site (citespace.podia.com) stopped offering the free Basic version in 2025. The FAQ states plainly:

> Due to our limited support resources, the previously available Basic (free) version is no longer offered.

Distribution is now subscription-based (as of Sept 2026):

| Plan | Price | License |
|------|-------|---------|
| Standard | $65 / year | 1 computer |
| Intermediate | $110 / year | 2 computers |
| Advanced | $155 / 2 years | 2 computers, GPT-powered cluster summarization |

Payment supports Alipay and WeChat Pay (see FAQ 2.2). The current Windows release is CiteSpace 7.0.2.

## 2. The expiry trap in "free" installers

The free installers circulating in older tutorials (6.2.R4, 6.3.1 Basic) show `Expire: December 31, 2025` in their About panel — the expiry check is built in, so they will most likely refuse to start now, no matter how recent the tutorial looks. Version 6.4.R2 Advanced runs until 2026-12-31 but is a paid product; "cracked" copies are a security risk, and the official site states that any channel other than podia is unauthorized.

Bottom line: **for long-term use in 2026, the only legitimate route is a subscription.** Old versions are fine for a quick trial, but do not rely on them.

## 3. Channels surveyed (Sept 2026)

- Official site: citespace.podia.com — register, subscribe, download. Most reliable.
- SourceForge (sourceforge.net/projects/citespace): once mentioned in the official FAQ for free versions; files have been removed.
- Various net disks (Baidu/Quark/Xunlei): old versions such as 6.3.1 still circulate; mind the expiry and run antivirus.
- Li Jie's (CiteSpace co-developer) official resource library: citespace.lanzoub.com/b0koc51pi (password 32i5) — contains the Chinese guide (7th ed.), the fourth edition of the textbook, and sample datasets. Worth downloading before the software itself.

## 4. Installation tips

1. The install path must be pure ASCII without spaces, e.g. `D:\Program Files\CiteSpace`. Non-ASCII paths are the most common cause of startup failures.
2. Versions 6.x/7.x bundle their own Java runtime — no separate JDK needed.
3. On first launch, switch English → 中文简体 on the welcome screen, then click Agree.
4. If startup fails or the console window hangs: delete `C:\Users\<you>\.citespace` and retry; then check for conflicting Java installations.
5. For large datasets (tens of thousands of records), raise the JVM heap in the launch script (e.g. `-Xmx4g`).

## 5. Free alternatives

For co-occurrence and collaboration networks alone, VOSviewer (vosviewer.com) is free and lighter; biblioshiny (R) suits full-scale science-mapping workflows. Both accept plain-text WoS exports directly.

---

References: CiteSpace official FAQ (citespace.podia.com/faq); Chaomei Chen, *How to Use CiteSpace*.
