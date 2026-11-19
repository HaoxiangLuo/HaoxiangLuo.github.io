(function () {
  "use strict";

  document.querySelectorAll("[data-project-video]").forEach(function (stage) {
    var video = stage.querySelector("video");
    var play = stage.querySelector("[data-project-play]");

    play.hidden = false;
    play.addEventListener("click", function () {
      video.play().catch(function () { video.focus(); });
    });
    video.addEventListener("playing", function () {
      if (document.activeElement === play) video.focus();
      play.hidden = true;
    });
    video.addEventListener("ended", function () { play.hidden = false; });
  });
}());
