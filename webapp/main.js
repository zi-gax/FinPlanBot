// Initialize Telegram Web App
const twa = window.Telegram.WebApp;

// Expand the app to full height
twa.expand();

// Set up UI components
const mainBtn = document.getElementById('main-btn');

// Example interaction
mainBtn.addEventListener('click', () => {
    twa.HapticFeedback.impactOccurred('medium');
    twa.showAlert("We'll notify you as soon as we're live!");
});

// Update theme colors if needed (Telegram provides dynamic theme colors)
if (twa.colorScheme === 'light') {
    // Optional: adjustments for light mode if the design allowed it
    // But our design is a sleek dark mode by default
}

console.log('Coming Soon App Initialized');
