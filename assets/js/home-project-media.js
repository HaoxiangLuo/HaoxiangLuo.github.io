(function () {
  "use strict";

  const links = document.querySelectorAll("[data-home-media]");
  if (!links.length || !window.HTMLDialogElement || !HTMLDialogElement.prototype.showModal) return;

  const dialog = document.createElement("dialog");
  dialog.className = "home-media-dialog";
  dialog.setAttribute("aria-labelledby", "home-media-title");
  const header = document.createElement("header");
  header.className = "home-media-dialog__header";
  const title = document.createElement("h2");
  title.id = "home-media-title";
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = document.documentElement.lang.startsWith("zh") ? "关闭" : "Close";
  const body = document.createElement("div");
  body.className = "home-media-dialog__body";
  header.append(title, close);
  dialog.append(header, body);
  document.body.append(dialog);

  let trigger;
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    const video = body.querySelector("video");
    if (video) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
    body.replaceChildren();
    trigger?.focus({ preventScroll: true });
  });

  for (const link of links) {
    link.setAttribute("aria-haspopup", "dialog");
    link.addEventListener("click", (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      trigger = link;
      title.textContent = link.dataset.mediaTitle;
      const isVideo = link.dataset.homeMedia === "video";
      const media = document.createElement(isVideo ? "video" : "img");
      if (isVideo) {
        media.controls = true;
        media.playsInline = true;
        media.poster = link.querySelector("img").currentSrc || link.querySelector("img").src;
        media.setAttribute("aria-label", link.dataset.mediaLabel);
      } else {
        media.alt = link.dataset.mediaLabel;
      }
      media.src = link.href;
      body.replaceChildren(media);
      dialog.showModal();
      if (isVideo) media.play().catch(() => { /* Native controls remain available. */ });
    });
  }
})();
