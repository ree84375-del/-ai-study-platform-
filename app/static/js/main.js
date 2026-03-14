// main logic can go here
console.log("AI Study Platform Initialized");

// Auto-hide flash messages after 1.5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        setTimeout(function() {
            alerts.forEach(function(alert) {
                alert.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(function() {
                    alert.remove();
                }, 500);
            });
        }, 1500);
    }
});
async function toggleDarkMode() {
    try {
        const response = await fetch('/api/toggle_dark_mode', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        });
        const data = await response.json();
        if (data.status === 'success') {
            location.reload(); // Reload to apply the new CSS variables from the backend
        }
    } catch (err) {
        console.error("Theme toggle failed:", err);
    }
}
