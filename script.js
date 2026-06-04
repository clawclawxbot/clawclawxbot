// SYNDICAT — scroll reveal + animated stat counters

// 1) Reveal sections as they enter the viewport
const revealer = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      e.target.classList.add("in");
      revealer.unobserve(e.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll(".section").forEach((s) => revealer.observe(s));

// 2) Count-up animation for the stat badges
function animateCount(el) {
  const target = parseInt(el.dataset.count, 10) || 0;
  const dur = 1400;
  const start = performance.now();
  function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
    el.textContent = Math.floor(eased * target).toLocaleString("en-US");
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

const counter = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      animateCount(e.target);
      counter.unobserve(e.target);
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll("[data-count]").forEach((b) => counter.observe(b));

// 3) Mobile navbar toggle
const nav = document.querySelector(".nav");
const toggle = document.querySelector(".nav__toggle");
if (nav && toggle) {
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  // close the menu after tapping a link
  nav.querySelectorAll(".nav__menu a").forEach((a) =>
    a.addEventListener("click", () => {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    })
  );
}

// 4) Copy-to-clipboard buttons (e.g. token contract address)
document.querySelectorAll(".copy-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = btn.dataset.copy || "";
    try {
      await navigator.clipboard.writeText(text);
      const original = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = original), 1500);
    } catch {
      btn.textContent = "Copy failed";
    }
  });
});

// 5) Launch countdown
document.querySelectorAll(".countdown").forEach((cd) => {
  const deadline = new Date(cd.dataset.deadline).getTime();
  const out = {
    days: cd.querySelector('[data-cd="days"]'),
    hours: cd.querySelector('[data-cd="hours"]'),
    mins: cd.querySelector('[data-cd="mins"]'),
    secs: cd.querySelector('[data-cd="secs"]'),
  };
  const pad = (n) => String(n).padStart(2, "0");
  let timer;
  function tick() {
    const diff = deadline - Date.now();
    if (diff <= 0) {
      Object.values(out).forEach((el) => el && (el.textContent = "00"));
      const lbl = cd.parentElement && cd.parentElement.querySelector(".cd-label");
      if (lbl) lbl.textContent = "🚀 $CLAWX is live!";
      if (timer) clearInterval(timer);
      return;
    }
    const s = Math.floor(diff / 1000);
    if (out.days) out.days.textContent = pad(Math.floor(s / 86400));
    if (out.hours) out.hours.textContent = pad(Math.floor((s % 86400) / 3600));
    if (out.mins) out.mins.textContent = pad(Math.floor((s % 3600) / 60));
    if (out.secs) out.secs.textContent = pad(s % 60);
  }
  tick();
  timer = setInterval(tick, 1000);
});

// 6) Typewriter loop on the CTA title ("Start in Telegram.")
(function () {
  var el = document.querySelector(".cta__title");
  if (!el) return;
  var full = (el.textContent || "").trim() || "Start in Telegram.";
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = full; return; }
  el.classList.add("typewriter");
  var i = 0, dir = 1;
  function step() {
    el.textContent = full.slice(0, i);
    var delay = dir > 0 ? 110 : 55;          // typing speed (not too fast) / deleting speed
    if (dir > 0 && i === full.length) { dir = -1; delay = 2000; }   // pause when full
    else if (dir < 0 && i === 0) { dir = 1; delay = 700; }          // pause when empty, then loop
    else { i += dir; }
    setTimeout(step, delay);
  }
  step();
})();
