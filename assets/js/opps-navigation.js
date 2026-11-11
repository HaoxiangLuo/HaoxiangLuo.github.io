/* Overview links reveal the relevant section before navigating to it. */
document.querySelectorAll('.opps-overview a[href^="#"]').forEach(function (link) {
  link.addEventListener('click', function (event) {
    var target = document.getElementById(link.getAttribute('href').slice(1));
    if (!target) return;
    event.preventDefault();
    for (var parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    target.scrollIntoView({ behavior: 'instant', block: 'start' });
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });
});
