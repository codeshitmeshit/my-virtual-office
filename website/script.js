// i18n helper
const _t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// Nav background on scroll
const nav = document.querySelector('.nav');
window.addEventListener('scroll', () => {
    nav.classList.toggle('is-scrolled', window.scrollY > 20);
});

// Simple intersection observer for fade-in
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
        }
    });
}, { threshold: 0.1 });

document.querySelectorAll('.feature-card, .demo-card, .pricing-card, .faq-item, .setup-step').forEach(el => {
    el.classList.add('is-reveal-pending');
    observer.observe(el);
});
