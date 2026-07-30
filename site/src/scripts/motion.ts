// Sitewide "Notebook Depth" motion (DESIGN.md §9 / UX.md §3, 2026-07-30
// exception). Every element this touches renders fully visible, in its
// final position, in plain server-rendered HTML (DESIGN.md §9's binding
// no-JS rule) — this script only ever animates FROM that visible state, and
// only for elements not already in the viewport when it runs, so nothing
// ever flashes hidden-then-visible on load (the classic reveal-on-scroll
// FOUC bug). prefers-reduced-motion is handled separately from global.css's
// CSS kill-switch, via gsap.matchMedia() below — GSAP animates via
// requestAnimationFrame, not the transition/animation CSS properties, so the
// CSS media query can't reach it.
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";

gsap.registerPlugin(ScrollTrigger, SplitText);

const PARALLAX_SELECTOR = "[data-parallax]";
const HAIRLINE_SELECTOR = ".draw-line-on-view";
// Author prose flows through MDX (<Content components={{ Pull, TippedPhoto }} />)
// with no rehype/remark pass to inject a class per paragraph, so reading-spine
// text is targeted by scoped selector; VenueEntry/Pull carry an explicit
// data-reveal-lines attribute instead since those are hand-authored components.
const REVEAL_SELECTOR = [".reading-spine > p", ".reading-spine > h2", ".reading-spine > h3", "[data-reveal-lines]"].join(
  ", ",
);
const MAX_STAGGER_LINES = 9;

let splitInstances: SplitText[] = [];
let matchMedia: ReturnType<typeof gsap.matchMedia> | null = null;
let resizeListenerAttached = false;
let resizeTimer: ReturnType<typeof setTimeout> | undefined;

function inViewportNow(el: Element): boolean {
  const rect = el.getBoundingClientRect();
  return rect.top < window.innerHeight && rect.bottom > 0;
}

function parallaxMaxPx(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--motion-parallax-max");
  return parseFloat(raw) || 40;
}

function setupParallax() {
  const max = parallaxMaxPx();
  document.querySelectorAll<HTMLElement>(PARALLAX_SELECTOR).forEach((el) => {
    gsap.fromTo(
      el,
      { y: -max / 2 },
      {
        y: max / 2,
        ease: "none",
        scrollTrigger: { trigger: el, start: "top bottom", end: "bottom top", scrub: true },
      },
    );
  });
}

function setupHairlines() {
  document.querySelectorAll<HTMLElement>(HAIRLINE_SELECTOR).forEach((el) => {
    if (inViewportNow(el)) return; // already visible — leave it alone, no FOUC
    gsap.fromTo(
      el,
      { scaleX: 0 },
      {
        scaleX: 1,
        duration: 0.9,
        ease: "power2.out",
        scrollTrigger: { trigger: el, start: "top 85%", once: true },
      },
    );
  });
}

function setupLineReveal() {
  document.querySelectorAll<HTMLElement>(REVEAL_SELECTOR).forEach((el) => {
    if (!el.textContent?.trim()) return;
    const alreadyVisible = inViewportNow(el);
    const split = new SplitText(el, { type: "lines", linesClass: "reveal-line" });
    splitInstances.push(split);
    if (alreadyVisible) return; // leave already-visible content alone

    const staggerLines = split.lines.slice(0, MAX_STAGGER_LINES);
    const remainder = split.lines.slice(MAX_STAGGER_LINES);
    const trigger = { trigger: el, start: "top 85%", once: true };

    gsap.fromTo(
      staggerLines,
      { opacity: 0, y: 10 },
      { opacity: 1, y: 0, duration: 0.7, ease: "power2.out", stagger: 0.06, scrollTrigger: trigger },
    );
    // A run longer than MAX_STAGGER_LINES compresses rather than keeps
    // stretching, so no block ever meaningfully outruns the rest of the
    // site's ~0.7-0.9s motion family (DESIGN.md §9).
    if (remainder.length > 0) {
      gsap.fromTo(
        remainder,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.7, ease: "power2.out", scrollTrigger: trigger },
      );
    }
  });
}

function cleanup() {
  ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
  splitInstances.forEach((split) => split.revert());
  splitInstances = [];
  matchMedia?.revert();
  matchMedia = null;
}

// Re-run on every astro:page-load (fires on the first load AND every
// subsequent <ClientRouter /> navigation), and on resize — SplitText's line
// breaks depend on viewport width and this site's font-display: swap
// variable fonts, so old splits/triggers are torn down and rebuilt each time
// rather than patched in place.
export async function initMotion() {
  cleanup();
  if (document.fonts?.ready) {
    try {
      await document.fonts.ready;
    } catch {
      // proceed with whatever layout is current rather than block indefinitely
    }
  }

  matchMedia = gsap.matchMedia();
  matchMedia.add("(prefers-reduced-motion: no-preference)", () => {
    setupParallax();
    setupHairlines();
    setupLineReveal();
  });
  ScrollTrigger.refresh();

  if (!resizeListenerAttached) {
    resizeListenerAttached = true;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => void initMotion(), 200);
    });
  }
}
