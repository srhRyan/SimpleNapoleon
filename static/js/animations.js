/**
 * Animation module — extensible hooks for UI/UX animations.
 *
 * Each function receives DOM elements and applies CSS classes or
 * inline styles. Replace or extend these with GSAP / anime.js / etc.
 * for richer animations in the future.
 */

const Animations = (() => {
  /**
   * Apply a named animation to an element.
   * Uses data-anim attribute which triggers CSS @keyframes.
   */
  function play(el, animName, durationMs = 400) {
    if (!el) return Promise.resolve();
    return new Promise(resolve => {
      el.setAttribute('data-anim', animName);
      const handler = () => {
        el.removeAttribute('data-anim');
        el.removeEventListener('animationend', handler);
        resolve();
      };
      el.addEventListener('animationend', handler);
      // Fallback timeout
      setTimeout(() => {
        el.removeAttribute('data-anim');
        resolve();
      }, durationMs + 100);
    });
  }

  /** Animate dealing cards into the hand area. */
  function dealCards(cardEls) {
    cardEls.forEach((el, i) => {
      el.style.animationDelay = `${i * 30}ms`;
      play(el, 'deal', 300 + i * 30);
    });
  }

  /** Animate a card being played to the trick area. */
  function playCard(trickCardEl) {
    return play(trickCardEl, 'play', 400);
  }

  /** Animate trick win highlight. */
  function trickWin(trickCardEls) {
    trickCardEls.forEach(el => play(el, 'win', 600));
  }

  /** Flash a message in the center of the table. */
  function showCenterMessage(msg, durationMs = 1500) {
    const el = document.getElementById('center-msg');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), durationMs);
  }

  /** Fade in an element. */
  function fadeIn(el) {
    if (!el) return;
    el.classList.add('fade-in');
    el.addEventListener('animationend', () => el.classList.remove('fade-in'), { once: true });
  }

  /** Pop-in effect. */
  function popIn(el) {
    if (!el) return;
    el.classList.add('pop-in');
    el.addEventListener('animationend', () => el.classList.remove('pop-in'), { once: true });
  }

  return { play, dealCards, playCard, trickWin, showCenterMessage, fadeIn, popIn };
})();
