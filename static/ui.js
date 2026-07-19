// ── ui.js — общие микро-механики дизайн-системы ─────────────────────────────
// 1. running-border: вычисляет периметр каждой .btn-signature и пишет его
//    в CSS-переменную --perimeter (design-system.md, раздел 3 — не хардкодим).
// 2. scroll-reveal: элементы .reveal получают .revealed при входе в viewport.

(function () {
  'use strict';

  // ── Running-border у .btn-signature ──
  function initSignatureBorders() {
    document.querySelectorAll('.btn-signature').forEach(function (btn) {
      var rect = btn.querySelector('.signature-border rect');
      if (!rect) return;
      // размеры атрибутами — проценты в getTotalLength() не считаются
      var w = btn.offsetWidth, h = btn.offsetHeight;
      if (!w || !h) return;
      rect.setAttribute('width', w - 1);
      rect.setAttribute('height', h - 1);
      var perimeter = Math.ceil(rect.getTotalLength());
      btn.style.setProperty('--perimeter', perimeter);
    });
  }

  // ── Появление секций при скролле ──
  function initScrollReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!els.length || !('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('revealed'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  // ── Дропдаун аватара в шапке ──
  function initAvatarDropdown() {
    var wrap = document.getElementById('avatar-wrap');
    if (!wrap) return;
    var btn = wrap.querySelector('.avatar-btn');
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = wrap.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function () {
      wrap.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  function init() {
    initSignatureBorders();
    initScrollReveal();
    initAvatarDropdown();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // при ресайзе периметр меняется — пересчитываем
  window.addEventListener('resize', initSignatureBorders);
})();
