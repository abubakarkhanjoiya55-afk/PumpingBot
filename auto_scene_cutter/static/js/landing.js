(() => {
  const nav = document.querySelector(".lp-nav");
  const video = document.querySelector(".lp-hero-video");

  function onScroll() {
    if (!nav) return;
    nav.classList.toggle("is-solid", window.scrollY > 24);
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Respect reduced motion
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches && video) {
    video.removeAttribute("autoplay");
    try {
      video.pause();
    } catch (_) {
      /* ignore */
    }
  }

  // Reveal sections lightly when in view
  const sections = document.querySelectorAll(".lp-section");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) e.target.classList.add("is-in");
        });
      },
      { threshold: 0.15 }
    );
    sections.forEach((s) => io.observe(s));
  }
})();
