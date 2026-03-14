/**
 * AI Study Platform - Main JavaScript
 * Handles: Theme Management, Falling Leaf Animations, Micro-interactions
 */

document.addEventListener('DOMContentLoaded', () => {
    initThemeManager();
    initFlashHider();
});

/**
 * Theme Manager: Handles instant theme switching and persistence
 */
function initThemeManager() {
    // 1. Initial Apply: LocalStorage > User Data Attribute > System Default
    const savedTheme = localStorage.getItem('app-theme') || document.documentElement.getAttribute('data-theme') || 'sakura';
    applyTheme(savedTheme, false); // Don't save to storage on initial load to avoid redundant writes

    // 2. Global listener for theme changes (from settings or mobile toggle)
    window.addEventListener('theme-changed', (e) => {
        applyTheme(e.detail.theme);
    });
}

function applyTheme(theme, save = true) {
    document.documentElement.setAttribute('data-theme', theme);
    if (save) {
        localStorage.setItem('app-theme', theme);
        // Fallback: Try to sync with server if online/logged in
        syncThemeWithServer(theme);
    }
}

async function syncThemeWithServer(theme) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (!csrfToken) return;

    try {
        await fetch('/api/update_theme', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ theme: theme })
        });
    } catch (err) {
        console.warn("Theme sync failed, but LocalStorage is preserved.");
    }
}

/**
 * Flash Hider: Auto-dim missed messages
 */
function initFlashHider() {
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        setTimeout(() => {
            alerts.forEach(alert => {
                alert.style.transition = 'all 0.5s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-20px)';
                setTimeout(() => alert.remove(), 500);
            });
        }, 3000);
    }
}

/**
 * Global Theme Toggle helper for UI buttons
 */
function toggleDarkMode() {
    const current = document.documentElement.getAttribute('data-theme') || 'sakura';
    const next = current === 'midnight' ? 'sakura' : 'midnight';
    applyTheme(next);
}

function selectTheme(themeName) {
    applyTheme(themeName);
}
