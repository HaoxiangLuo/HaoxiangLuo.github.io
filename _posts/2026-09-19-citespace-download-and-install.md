---
title: "CiteSpace 下载与安装札记（2026 年版）"
excerpt: "CiteSpace 转向订阅制之后，免费版还能不能装、从哪里装：渠道梳理、版本有效期与安装要点。"
date: 2026-09-19
permalink: /posts/2026/09/citespace-download-and-install/
lang: zh
translation_url: /posts/2026/09/citespace-download-and-install-en/
categories:
  - 研究方法
tags:
  - 研究方法
  - 文献计量
  - CiteSpace
  - 知识图谱
---

做文献综述前重新配置了 CiteSpace，把 2026 年 9 月这一时点的下载渠道、版本有效期和安装要点记在这里，供以后换电脑时查阅。

## 一、现状：官方已转向订阅制

CiteSpace 官网（citespace.podia.com）自 2025 年起不再提供免费的 Basic 版本，官网 FAQ 原文：

> Due to our limited support resources, the previously available Basic (free) version is no longer offered.

目前官方分发方式为订阅授权（以 2026 年 9 月为准）：

| 方案 | 价格 | 授权 |
|------|------|------|
| Standard | $65 / 年 | 1 台电脑 |
| Intermediate | $110 / 年 | 2 台电脑 |
| Advanced | $155 / 2 年 | 2 台电脑，含 GPT 集群摘要等功能 |

支持支付宝与微信付款（见官网 FAQ 2.2），付款需提供邮箱用于激活。当前 Windows 最新版本为 CiteSpace 7.0.2。

## 二、免费旧版的"有效期"坑

网上大量教程推荐的免费安装包（6.2.R4、6.3.1 Basic）在软件信息面板里写着 `Expire: December 31, 2025`——这些版本内置有效期校验，现在安装大概率无法启动，教程年代再新也改变不了这一点。6.4.R2 Advanced 的有效期到 2026-12-31，但它是付费版，第三方"破解/激活版"存在安全风险，官网也明确声明非官网渠道均未授权。

结论：**2026 年想长期稳定使用 CiteSpace，正规途径只有订阅**；短期试用可以装旧版体验，但别指望它长期可用。

## 三、下载渠道梳理（2026-09 实测）

- 官网直装：citespace.podia.com —— 注册账号、订阅后下载，最可靠。
- SourceForge（sourceforge.net/projects/citespace）：官方 FAQ 曾提及的免费版下载地，实测文件已被清空。
- 各类网盘（百度/夸克/迅雷）：能找到 6.3.1 等旧版，注意过期问题与杀毒。
- 李杰老师（CiteSpace 中文合作开发者）的官方资料库：citespace.lanzoub.com/b0koc51pi（密码 32i5），内含《CiteSpace 中文指南（第 7 版）》《科技文本挖掘及可视化（第四版）》与案例数据，比软件本身更值得先下载。

## 四、安装要点

1. 安装路径必须纯英文、无空格，例如 `D:\Program Files\CiteSpace`。中文路径是启动失败的常见原因。
2. 6.x / 7.x 版本自带 Java 运行环境（ installer 里 bundled），无需另装 JDK。
3. 首次启动在欢迎界面点 English 切换为"中文简体"，再点 Agree。
4. 启动异常（闪退/黑窗卡住）：删除 `C:\Users\<用户名>\.citespace` 文件夹后重试；仍失败再排查 Java 版本冲突。
5. 大数据量（数万条文献）出现内存不足时，调大启动脚本中的 JVM 堆参数（如 `-Xmx4g`）。

## 五、本机的目录方案

我把 CiteSpace 相关内容统一放在 `D:\CiteSpace`：

```
D:\CiteSpace\
├── 01-安装包\    # 安装程序
├── 02-教程资料\  # 中文指南、案例讲义
├── 03-数据\      # WoS/CNKI 导出数据、案例数据
└── 04-项目\      # 各分析项目（project + data 成对存放）
```

软件内建项目路径指向这里，换电脑时备份这个目录即可。

## 六、免费替代方案

若只是绘制文献共现与合作网络，VOSviewer（vosviewer.com）完全免费、更轻量；biblioshiny（R 语言）适合做科学计量全景分析。两者与 CiteSpace 数据格式互通性都不错，WoS 导出的纯文本可直接导入。

---

参考：CiteSpace 官网 FAQ（citespace.podia.com/faq）；陈超美《How to Use CiteSpace》。
