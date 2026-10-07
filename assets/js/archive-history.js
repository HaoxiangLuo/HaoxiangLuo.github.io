/*!
 * On-demand loading of the long-term JSONL archives.
 *
 * The default pages only carry the recent index that Jekyll built from the
 * archive. When a visitor picks a year or month that the index no longer holds,
 * this module reads `manifest.json`, fetches the matching partition, parses it
 * line by line and hands the records to the renderer registered for that
 * dataset.
 *
 * Rules that keep the pages light:
 *  - nothing is fetched until a visitor asks for an earlier period;
 *  - partitions are cached in memory, so the same file is never downloaded twice;
 *  - a failed load leaves everything already on screen untouched.
 *
 * No framework, no external service: `fetch()` and the DOM only.
 */
(function () {
  "use strict";

  var MANIFEST_URL = "/assets/data/archive/manifest.json";

  var DATASETS = {
    daily_news: { container: ".daily-news-archive", partition: "monthly" },
    academic_frontiers: { container: ".frontiers-archive", partition: "yearly" },
    site_updates: { container: ".site-timeline", partition: "yearly" }
  };

  var LABELS = {
    en: {
      loading: "Loading archived records…",
      error: "The archived records could not be loaded.",
      empty: "No archived records are available for this period.",
      retry: "Retry",
      headlines: "headlines",
      headline: "headline",
      updates: "updates",
      update: "update",
      authorsMissing: "Authors are not listed in the metadata.",
      abstractMissing: "No abstract excerpt is available in the metadata.",
      abstractLabel: "Abstract excerpt",
      originalAbstract: "Original abstract",
      readSource: "Read source",
      viewCommit: "View commit"
    },
    zh: {
      loading: "正在读取历史归档…",
      error: "历史归档暂时无法读取。",
      empty: "该时间段没有可读取的归档记录。",
      retry: "重试",
      headlines: "条简讯",
      headline: "条简讯",
      updates: "项更新",
      update: "项更新",
      authorsMissing: "元数据中未列出作者。",
      abstractMissing: "元数据中暂无摘要节选。",
      abstractLabel: "摘要节选",
      originalAbstract: "英文原文",
      readSource: "阅读原文",
      viewCommit: "查看提交"
    }
  };

  var cache = {};
  var manifestPromise = null;

  function labels(language) {
    return language === "zh" ? LABELS.zh : LABELS.en;
  }

  function datasetSpec(dataset) {
    return DATASETS[dataset] || null;
  }

  function containerFor(dataset) {
    var spec = datasetSpec(dataset);
    return spec ? document.querySelector(spec.container) : null;
  }

  function setText(node, value) {
    node.textContent = value === null || value === undefined ? "" : String(value);
    return node;
  }

  function parseJSONL(text) {
    var records = [];
    var lines = String(text || "").split("\n");
    for (var index = 0; index < lines.length; index += 1) {
      var line = lines[index].trim();
      if (!line) continue;
      try {
        var record = JSON.parse(line);
        if (record && typeof record === "object") records.push(record);
      } catch (error) {
        // A broken line is skipped rather than failing the whole partition.
      }
    }
    return records;
  }

  function fetchText(url) {
    return fetch(url, { credentials: "omit" }).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.text();
    });
  }

  function loadManifest() {
    if (!manifestPromise) {
      manifestPromise = fetchText(MANIFEST_URL).then(function (text) {
        var parsed = JSON.parse(text);
        return (parsed && parsed.archives) || {};
      }).catch(function (error) {
        manifestPromise = null; // let a retry fetch the manifest again
        throw error;
      });
    }
    return manifestPromise;
  }

  function loadPartition(url) {
    if (!cache[url]) {
      cache[url] = fetchText(url).then(parseJSONL).catch(function (error) {
        delete cache[url];
        throw error;
      });
    }
    return cache[url];
  }

  function partitionKeys(dataset, year, month) {
    var spec = datasetSpec(dataset);
    if (!spec) return [];
    if (spec.partition === "monthly") {
      return month && month !== "all" ? [year + "-" + month] : [year + "-"]; // prefix: every month of the year
    }
    return [year];
  }

  /*!
   * Load every partition that can answer the selected period.
   *
   * `covered` holds the periods the recent index already shows; those are
   * skipped so a visitor never downloads data the page already rendered.
   */
  function loadRange(dataset, year, month, covered) {
    var wanted = partitionKeys(dataset, year, month);
    if (!wanted.length) return Promise.resolve([]);

    return loadManifest().then(function (archives) {
      var entry = archives[dataset] || {};
      var available = entry.available || [];
      var urls = [];
      available.forEach(function (part) {
        var key = String(part.key || "");
        var matches = wanted.some(function (need) {
          return need.slice(-1) === "-" ? key.indexOf(need) === 0 : key === need;
        });
        if (!matches) return;
        if (covered && covered[key]) return; // already on the page
        if (part.url) urls.push(part.url);
      });
      if (!urls.length) return [];

      return Promise.all(urls.map(loadPartition)).then(function (groups) {
        var records = [];
        var seen = {};
        groups.forEach(function (group) {
          group.forEach(function (record) {
            var identity = record.id || (record.date || "") + "|" + (record.title || "");
            if (!identity || seen[identity]) return;
            seen[identity] = true;
            records.push(record);
          });
        });
        return records;
      });
    });
  }

  function formatDate(value, language) {
    var parts = String(value || "").split("-");
    if (parts.length !== 3) return String(value || "");
    var date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (isNaN(date.getTime())) return String(value || "");
    return new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en", {
      year: "numeric",
      month: "long",
      day: "numeric"
    }).format(date);
  }

  function renderDailyNews(container, records, options) {
    var words = labels(options.language);
    var rendered = 0;
    records.forEach(function (record) {
      var date = record.date || "";
      if (!date) return;
      if (container.querySelector('[data-filter-date="' + date + '"]')) return; // already shown

      var section = document.createElement("section");
      section.className = "daily-news-day";
      section.setAttribute("data-filter-date", date);
      section.setAttribute("data-archive-record", "true");

      var header = document.createElement("header");
      var time = document.createElement("time");
      time.dateTime = date;
      setText(time, formatDate(date, options.language));
      var count = document.createElement("span");
      var items = record.items || [];
      setText(count, options.language === "zh"
        ? items.length + " " + words.headlines
        : items.length + " " + (items.length === 1 ? words.headline : words.headlines));
      header.appendChild(time);
      header.appendChild(count);

      var list = document.createElement("ol");
      items.forEach(function (item) {
        var row = document.createElement("li");
        var link = document.createElement("a");
        link.href = item.url || "#";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        var title = document.createElement("span");
        setText(title, options.language === "zh" && item.title_zh ? item.title_zh : item.title);
        var source = document.createElement("small");
        setText(source, item.source || "");
        var arrow = document.createElement("b");
        arrow.setAttribute("aria-hidden", "true");
        setText(arrow, "↗");
        source.appendChild(document.createTextNode(" "));
        source.appendChild(arrow);
        link.appendChild(title);
        link.appendChild(source);
        row.appendChild(link);
        list.appendChild(row);
      });

      section.appendChild(header);
      section.appendChild(list);
      container.appendChild(section);
      rendered += 1;
    });
    return rendered;
  }

  function renderFrontiers(container, records, options) {
    var words = labels(options.language);
    var rendered = 0;
    records.forEach(function (record) {
      var date = record.published_at || "";
      if (!date) return;
      var title = record.title || "";
      if (container.querySelector('[data-archive-id="' + String(record.id || "").replace(/"/g, "") + '"]')) return;
      if (title && container.querySelector('[data-archive-title="' + title.replace(/"/g, "") + '"]')) return;

      var card = document.createElement("article");
      card.className = "frontiers-card";
      card.setAttribute("data-filter-date", date);
      card.setAttribute("data-archive-record", "true");
      card.setAttribute("data-archive-id", record.id || "");
      card.setAttribute("data-archive-title", title);

      var meta = document.createElement("header");
      meta.className = "frontiers-card__meta";
      var time = document.createElement("time");
      time.dateTime = date;
      setText(time, formatDate(date, options.language));
      meta.appendChild(time);
      if (record.journal) {
        var journal = document.createElement("span");
        journal.className = "frontiers-card__journal";
        setText(journal, record.journal);
        meta.appendChild(journal);
      }
      if (record.source_tier) {
        var tier = document.createElement("span");
        tier.className = "frontiers-card__tier";
        setText(tier, record.source_tier);
        meta.appendChild(tier);
      }

      // The Chinese wording is what is read; the wording the paper was
      // published under stays on the card so it can still be found.
      var useChinese = options.language === "zh";
      var zhTitle = useChinese ? record.title_zh : "";
      var zhAbstract = useChinese ? record.abstract_excerpt_zh : "";

      var heading = document.createElement("h2");
      heading.className = "frontiers-card__title";
      setText(heading, zhTitle || title);

      var authors = document.createElement("p");
      authors.className = "frontiers-card__authors";
      var names = record.authors || [];
      setText(authors, names.length ? names.join(", ") : words.authorsMissing);

      var abstract = document.createElement("p");
      abstract.className = "frontiers-card__abstract" + ((zhAbstract || record.abstract_excerpt) ? "" : " is-empty");
      var label = document.createElement("span");
      label.className = "frontiers-card__label";
      setText(label, words.abstractLabel);
      abstract.appendChild(label);
      abstract.appendChild(document.createTextNode(" "));
      abstract.appendChild(document.createTextNode(zhAbstract || record.abstract_excerpt || words.abstractMissing));

      card.appendChild(meta);
      card.appendChild(heading);
      if (zhTitle && title) {
        var originalTitle = document.createElement("p");
        originalTitle.className = "frontiers-card__original";
        originalTitle.lang = "en";
        setText(originalTitle, title);
        card.appendChild(originalTitle);
      }
      card.appendChild(authors);
      card.appendChild(abstract);
      if (zhAbstract && record.abstract_excerpt) {
        var originalBlock = document.createElement("details");
        originalBlock.className = "frontiers-card__original-block";
        var summary = document.createElement("summary");
        setText(summary, words.originalAbstract);
        originalBlock.appendChild(summary);
        var originalAbstract = document.createElement("p");
        originalAbstract.className = "frontiers-card__abstract frontiers-card__abstract--original";
        originalAbstract.lang = "en";
        setText(originalAbstract, record.abstract_excerpt);
        originalBlock.appendChild(originalAbstract);
        card.appendChild(originalBlock);
      }

      var link = record.doi_url || record.landing_page_url;
      if (link) {
        var anchor = document.createElement("a");
        anchor.className = "frontiers-card__link";
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        setText(anchor, words.readSource + " ");
        var arrow = document.createElement("b");
        arrow.setAttribute("aria-hidden", "true");
        setText(arrow, "↗");
        anchor.appendChild(arrow);
        card.appendChild(anchor);
      }

      container.appendChild(card);
      rendered += 1;
    });
    return rendered;
  }

  function dayMarker(date, language) {
    var parts = String(date || "").split("-");
    var marker = document.createElement("time");
    marker.dateTime = date;
    var month = document.createElement("span");
    var day = document.createElement("strong");
    var year = document.createElement("small");
    if (parts.length === 3) {
      setText(month, language === "zh" ? Number(parts[1]) + "月" : parts[1]);
      setText(day, parts[2]);
      setText(year, parts[0]);
    }
    marker.appendChild(month);
    marker.appendChild(day);
    marker.appendChild(year);
    return marker;
  }

  function logEntry(record, options) {
    var words = labels(options.language);
    var section = document.createElement("section");
    section.className = "site-log-entry";
    if (record.sha) section.id = "update-" + record.sha;

    var head = document.createElement("div");
    head.className = "site-log-entry__head";
    var issue = document.createElement("span");
    issue.className = "site-log-entry__issue";
    setText(issue, record.sha || "");
    head.appendChild(issue);
    if (record.url) {
      var edit = document.createElement("a");
      edit.className = "site-log-entry__edit";
      edit.href = record.url;
      edit.target = "_blank";
      edit.rel = "noopener noreferrer";
      var editText = document.createElement("span");
      setText(editText, words.viewCommit);
      edit.appendChild(editText);
      head.appendChild(edit);
    }

    var heading = document.createElement("h3");
    setText(heading, options.language === "zh" ? record.title_zh : record.title_en);
    var story = document.createElement("p");
    story.className = "site-log-entry__story";
    var body = options.language === "zh"
      ? record.story_zh || record.details_zh || record.message || ""
      : record.story_en || record.details_en || record.message || "";
    setText(story, body);

    section.appendChild(head);
    section.appendChild(heading);
    section.appendChild(story);
    return section;
  }

  function renderSiteUpdates(container, records, options) {
    var words = labels(options.language);
    var byDate = {};
    var order = [];
    records.forEach(function (record) {
      var date = record.date || "";
      if (!date) return;
      if (!byDate[date]) {
        byDate[date] = [];
        order.push(date);
      }
      byDate[date].push(record);
    });

    var rendered = 0;
    order.forEach(function (date) {
      var day = container.querySelector('.site-log-day[data-filter-date="' + date + '"]');
      var items = day ? day.querySelector(".site-log-day__items") : null;
      var created = false;

      if (!day || !items) {
        day = document.createElement("article");
        day.className = "site-log-day";
        day.setAttribute("data-filter-date", date);
        day.setAttribute("data-archive-record", "true");
        day.appendChild(dayMarker(date, options.language));
        var card = document.createElement("div");
        card.className = "site-log-day__card";
        var header = document.createElement("header");
        header.className = "site-log-day__header";
        var heading = document.createElement("h2");
        setText(heading, formatDate(date, options.language));
        var counter = document.createElement("span");
        counter.className = "site-log-day__count";
        header.appendChild(heading);
        header.appendChild(counter);
        items = document.createElement("div");
        items.className = "site-log-day__items";
        card.appendChild(header);
        card.appendChild(items);
        day.appendChild(card);
        container.appendChild(day);
        created = true;
      }

      var added = 0;
      byDate[date].forEach(function (record) {
        if (record.sha && container.querySelector("#update-" + record.sha)) return;
        items.appendChild(logEntry(record, options));
        added += 1;
      });

      var counter = day.querySelector(".site-log-day__count");
      if (counter) {
        var total = items.querySelectorAll(".site-log-entry").length;
        setText(counter, options.language === "zh"
          ? "共 " + total + " " + words.updates
          : total + " " + (total === 1 ? words.update : words.updates));
      }
      if (added || created) rendered += 1;
    });
    return rendered;
  }

  var RENDERERS = {
    daily_news: renderDailyNews,
    academic_frontiers: renderFrontiers,
    site_updates: renderSiteUpdates
  };

  window.SiteArchiveHistory = {
    labels: labels,
    datasetSpec: datasetSpec,
    containerFor: containerFor,
    // The manifest is a tiny index, not the history itself: it lets the filter
    // offer years the recent index no longer carries.
    manifest: loadManifest,
    loadRange: loadRange,
    render: function (dataset, container, records, options) {
      var renderer = RENDERERS[dataset];
      if (!renderer || !container || !records) return 0;
      return renderer(container, records, options || {});
    }
  };
}());
