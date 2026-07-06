import { useEffect } from "react";

/**
 * Scroll-reveal: any element with .reveal / .reveal-scale gets .in added the
 * first time it enters the viewport. CSS owns the transition; per-element
 * stagger comes from an inline `--stagger` custom property.
 */
export default function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll(".reveal, .reveal-scale");
    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}
