import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useStudio } from "../App";

/** Shared, interruptible motion. Content remains visible when motion is unavailable. */
export function MotionEffects() {
  const { pathname, search } = useLocation();
  const { motionPaused, reducedMotion } = useStudio();
  useEffect(() => {
    const main = document.querySelector("#main");
    if (!main || motionPaused || reducedMotion) return;
    const animations = new Set<Animation>();
    const seen = new WeakSet<Element>();
    const ripples = new Set<HTMLElement>();
    let scanFrame = 0;
    const play = (element: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) => {
      const animation = element.animate(keyframes, options);
      animations.add(animation);
      animation.onfinish = () => animations.delete(animation);
      return animation;
    };
    const reveal = new IntersectionObserver(entries => {
      let position = 0;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        reveal.unobserve(entry.target);
        play(entry.target, [{ opacity: 0, transform: "translateY(24px)" }, { opacity: 1, transform: "translateY(0)" }],
          { duration: 600, delay: Math.min(position++ * 60, 180), easing: "cubic-bezier(.22,1,.36,1)" });
      }
    }, { threshold: .08 });
    const scan = () => {
      scanFrame = 0;
      main.querySelectorAll(".home-topic,.home-reading,.paper-card,.info-panel,.reading-section,.evaluation-row,.metric-card,.upload-panel,.upload-aside,.library-empty,.admin-stats>div,.review-entry,.file-queue-row").forEach(element => {
        if (seen.has(element)) return;
        seen.add(element); reveal.observe(element);
      });
    };
    scan();
    const changes = new MutationObserver(() => { if (!scanFrame) scanFrame = requestAnimationFrame(scan); });
    changes.observe(main, { childList: true, subtree: true });
    const press = (event: PointerEvent) => {
      if (event.button !== 0 || !(event.target instanceof Element)) return;
      const target = event.target.closest<HTMLElement>(".button,.search-submit,.nav-link,.tool-item,.topic-selector button,.bookmark-button,.recent-pagination>button");
      if (!target || target.matches(":disabled")) return;
      const rect = target.getBoundingClientRect(), size = Math.max(rect.width, rect.height) * 2;
      const ripple = document.createElement("span");
      ripple.className = "press-ripple"; ripple.setAttribute("aria-hidden", "true");
      Object.assign(ripple.style, { width: size + "px", height: size + "px", left: event.clientX - rect.left - size / 2 + "px", top: event.clientY - rect.top - size / 2 + "px" });
      target.append(ripple); ripples.add(ripple);
      const animation = play(ripple, [{ opacity: .18, transform: "scale(0)" }, { opacity: 0, transform: "scale(1)" }], { duration: 550, easing: "cubic-bezier(.22,1,.36,1)" });
      animation.onfinish = () => { animations.delete(animation); ripples.delete(ripple); ripple.remove(); };
    };
    document.addEventListener("pointerdown", press);
    return () => {
      reveal.disconnect(); changes.disconnect(); cancelAnimationFrame(scanFrame);
      document.removeEventListener("pointerdown", press);
      animations.forEach(animation => animation.cancel());
      ripples.forEach(ripple => ripple.remove());
    };
  }, [pathname, search, motionPaused, reducedMotion]);
  // A local glint follows the pointer without moving controls or creating a render loop.
  useEffect(() => {
    if (motionPaused || reducedMotion || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const touched = new Set<HTMLElement>();
    let frame = 0;
    let surface: HTMLElement | null = null;
    let x = 0, y = 0;
    const reset = () => {
      cancelAnimationFrame(frame); frame = 0;
      touched.forEach(element => {
        element.style.removeProperty("--glass-x"); element.style.removeProperty("--glass-y");
      });
      touched.clear(); surface = null;
    };
    const move = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || !(event.target instanceof Element)) return;
      surface = event.target.closest<HTMLElement>(".search-form,.site-header");
      if (!surface) return;
      x = event.clientX; y = event.clientY;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (!surface || document.hidden) return;
        const rect = surface.getBoundingClientRect();
        surface.style.setProperty("--glass-x", x - rect.left + "px");
        surface.style.setProperty("--glass-y", y - rect.top + "px");
        touched.add(surface);
      });
    };
    const visibility = () => { if (document.hidden) reset(); };
    document.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", reset);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      reset();
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", reset);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [motionPaused, reducedMotion]);
  return <div className="page-scroll-progress" aria-hidden="true"/>;
}
