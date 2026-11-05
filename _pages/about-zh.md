---
permalink: /zh/
title: ""
author_profile: true
author: LuoZH
lang: zh
translation_url: /
---

<section class="home-intro-panel">
<h1>关于我</h1>

<p>你好！我是<strong>罗昊翔</strong>，南京大学新闻传播学博士研究生。</p>

<h2>研究兴趣</h2>
<ul>
  <li>全球传播中的不平等</li>
  <li>虚假信息的扩散与工具化应用</li>
</ul>
</section>

{% include daily-news-widget.html %}

{% assign publication_page = site.pages | where: "permalink", "/zh/publications/" | first %}
{% if publication_page %}
<section class="home-publications" aria-labelledby="home-publications-title">
  <div class="home-publications__heading"><h2 id="home-publications-title">论文发表</h2><a href="{{ base_path }}/zh/publications/">查看完整页面 ↗</a></div>
  {% assign publication_content = publication_page.content | split: '<script src=' | first %}
  {{ publication_content | markdownify }}
</section>
<script src="{{ base_path }}/assets/js/publications.js" defer></script>
{% endif %}
