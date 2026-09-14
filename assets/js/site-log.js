(function () {
  "use strict";

  var panel = document.querySelector(".site-auto-updates");
  if (!panel) return;

  var list = panel.querySelector(".site-auto-updates__list");
  var isChinese = panel.getAttribute("data-language") === "zh";
  var endpoint = "https://api.github.com/repos/HaoxiangLuo/HaoxiangLuo.github.io/commits?per_page=6";

  fetch(endpoint, { headers: { Accept: "application/vnd.github+json" } })
    .then(function (response) {
      if (!response.ok) throw new Error("GitHub request failed");
      return response.json();
    })
    .then(function (commits) {
      list.textContent = "";
      commits.forEach(function (item) {
        var row = document.createElement("li");
        var link = document.createElement("a");
        var message = document.createElement("strong");
        var date = document.createElement("time");
        var rawDate = item.commit && item.commit.author ? item.commit.author.date : "";
        var firstLine = item.commit && item.commit.message ? item.commit.message.split("\n")[0] : "Update";

        link.href = item.html_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        message.textContent = firstLine;
        date.dateTime = rawDate;
        date.textContent = new Intl.DateTimeFormat(isChinese ? "zh-CN" : "en", {
          year: "numeric", month: "short", day: "numeric"
        }).format(new Date(rawDate));
        link.appendChild(message);
        link.appendChild(date);
        row.appendChild(link);
        list.appendChild(row);
      });
    })
    .catch(function () {
      list.innerHTML = "";
      var fallback = document.createElement("li");
      fallback.className = "is-loading";
      fallback.textContent = isChinese ? "暂时无法读取自动更新记录。" : "Automatic updates are temporarily unavailable.";
      list.appendChild(fallback);
    });
}());
