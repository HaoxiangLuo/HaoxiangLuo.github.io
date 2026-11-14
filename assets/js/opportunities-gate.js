(function () {
  "use strict";
  var gate = document.getElementById("opps-gate");
  var content = document.getElementById("opps-protected");
  var form = document.getElementById("opps-gate-form");
  if (!gate || !content || !form) return;
  var input = document.getElementById("opps-gate-password");
  var message = document.getElementById("opps-gate-message");
  var submit = form.querySelector("button");
  var salt = gate.getAttribute("data-salt");
  var expected = gate.getAttribute("data-hash");
  var zh = gate.getAttribute("data-language") === "zh";
  var key = "opportunities-unlocked-v1";
  var fingerprint = salt + ":" + expected;

  function unlock() {
    gate.hidden = true;
    content.hidden = false;
  }
  try {
    if (salt && expected && localStorage.getItem(key) === fingerprint) unlock();
  } catch (e) { /* Browsing can continue without persistent storage. */ }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!salt || !expected || !window.crypto || !window.crypto.subtle) {
      message.textContent = zh ? "当前浏览器无法验证密码。" : "This browser cannot verify the password.";
      return;
    }
    submit.disabled = true;
    message.textContent = "";
    try {
      var bytes = new TextEncoder().encode(salt + input.value);
      var digest = await window.crypto.subtle.digest("SHA-256", bytes);
      var actual = Array.prototype.map.call(new Uint8Array(digest), function (n) {
        return n.toString(16).padStart(2, "0");
      }).join("");
      if (actual !== expected) {
        message.textContent = zh ? "密码不正确，请重试。" : "Incorrect password. Please try again.";
        input.select();
        return;
      }
      input.value = "";
      try { localStorage.setItem(key, fingerprint); } catch (e) {
        var notice = document.createElement("p");
        notice.className = "opps-gate__storage-notice";
        notice.setAttribute("role", "status");
        notice.textContent = zh ? "浏览器未保存解锁状态，下次需要重新输入。" : "This browser could not remember the unlock.";
        content.insertBefore(notice, content.firstChild);
      }
      unlock();
    } catch (e) {
      message.textContent = zh ? "验证失败，请重试。" : "Verification failed. Please try again.";
    } finally {
      submit.disabled = false;
    }
  });
}());
