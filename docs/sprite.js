(() => {
  'use strict';

  const FACTS = [
    '一张 4K PNG 原图约 12 MB；JPEG q85 后约 1.2 MB —— 体积缩小约 10 倍，肉眼几乎无差。',
    'SHA-256 前 24 位的碰撞概率约为 1 / 10¹⁴ —— 比连中两次彩票头奖还难。',
    '100 篇文章引用了同一张封面图，OSS 上只存 1 份。',
    '本工具识别 4 种图片语法：Markdown、HTML <img>、引用式、Obsidian wikilink —— 可任意混用。',
    '图片上传是并发的，默认 3 路；100 张图通常 10 秒内全部就位。',
    '代码块里的 ![](...) 不会被改 —— 解析器会跳过反引号、<script>、<style>、HTML 注释。',
    'GIF 和 SVG 永远原样保留 —— 压缩反而会破坏它们。',
  ];

  const HOLD_MS = 5400;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ---------- Fact cycler ----------
  const factEl = document.querySelector('.fact');
  let idx = 0;
  let factTimer = null;

  function renderFact() {
    if (!factEl) return;
    factEl.textContent = FACTS[idx % FACTS.length];
    idx += 1;
  }

  function startFacts() {
    if (factTimer || !factEl) return;
    renderFact();
    factTimer = window.setInterval(renderFact, HOLD_MS);
  }

  function stopFacts() {
    if (!factTimer) return;
    window.clearInterval(factTimer);
    factTimer = null;
  }

  if (factEl) {
    if (reducedMotion.matches) renderFact();
    else startFacts();
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopFacts();
      else if (!reducedMotion.matches) startFacts();
    });
    reducedMotion.addEventListener?.('change', (e) => {
      if (e.matches) { stopFacts(); renderFact(); }
      else startFacts();
    });
  }

  // ---------- Copy buttons ----------
  document.querySelectorAll('.copy-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-copy-target');
      const code = id && document.getElementById(id);
      if (!code) return;
      const text = code.textContent.trim();
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        sel.removeAllRanges();
        sel.addRange(range);
        try { document.execCommand('copy'); } catch {}
        sel.removeAllRanges();
      }
      const original = btn.textContent;
      btn.textContent = '已复制';
      btn.classList.add('is-copied');
      window.setTimeout(() => {
        btn.textContent = original;
        btn.classList.remove('is-copied');
      }, 1400);
    });
  });

  // ---------- Fake video timer + play button ----------
  const playFake = document.getElementById('play-fake');
  const tooltip = document.getElementById('video-tooltip');
  const timerEl = document.getElementById('video-timer');

  if (playFake && tooltip) {
    let tipTimer = null;
    playFake.addEventListener('click', () => {
      tooltip.classList.add('is-visible');
      tooltip.setAttribute('aria-hidden', 'false');
      if (tipTimer) window.clearTimeout(tipTimer);
      tipTimer = window.setTimeout(() => {
        tooltip.classList.remove('is-visible');
        tooltip.setAttribute('aria-hidden', 'true');
      }, 2000);
    });
  }

  // Slow ticking 00:00 / -- : -- counter, purely cosmetic
  if (timerEl && !reducedMotion.matches) {
    let t = 0;
    window.setInterval(() => {
      t = (t + 1) % 60;
      const mm = String(Math.floor(t / 1) % 60).padStart(2, '0');
      const ss = String((t * 3) % 60).padStart(2, '0');
      timerEl.textContent = `${mm}:${ss} / -- : --`;
    }, 1000);
  }

  // ---------- Scroll-reveal sections ----------
  const revealTargets = document.querySelectorAll('.section-head, .path-card, .feature, .terminal, .video-slot');
  if (revealTargets.length && 'IntersectionObserver' in window && !reducedMotion.matches) {
    revealTargets.forEach((el) => el.classList.add('reveal'));
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
    );
    revealTargets.forEach((el) => io.observe(el));
  }
})();
