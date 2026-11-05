---
permalink: /
title: ""
author_profile: true
lang: en
translation_url: /zh/
redirect_from:
  - /about/
  - /about.html
---

<section class="home-intro-panel">
<h1>About Me</h1>

<p>Hello! I am <strong>Haoxiang Luo</strong>, a PhD student in Journalism and Communication at Nanjing University.</p>

<h2>Research Interests</h2>
<ul>
  <li>Inequality in Global Communication</li>
  <li>The Spread and Instrumentalization of Misinformation</li>
</ul>
</section>

{% include daily-news-widget.html %}

{% assign publication_page = site.pages | where: "permalink", "/publications/" | first %}
{% if publication_page %}
<section class="home-publications" aria-labelledby="home-publications-title">
  <div class="home-publications__heading"><h2 id="home-publications-title">Publications</h2><a href="{{ base_path }}/publications/">View full page ↗</a></div>
  {% assign publication_content = publication_page.content | split: '<script src=' | first %}
  {{ publication_content | markdownify }}
</section>
<script src="{{ base_path }}/assets/js/publications.js" defer></script>
{% endif %}
