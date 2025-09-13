// Main JavaScript for Tutorial Platform

// Global variables
let completedModules = JSON.parse(localStorage.getItem('completed_modules') || '[]');
let bookmarkedModules = JSON.parse(localStorage.getItem('bookmarked_modules') || '[]');
let darkModeEnabled = localStorage.getItem('dark_mode') === 'true';

// Initialize dark mode
document.addEventListener('DOMContentLoaded', function() {
    initializeDarkMode();
    initializeProgress();
    initializeSearch();
    initializeKeyboardNavigation();
    initializeBookmarks();
});

// Dark Mode Functions
function initializeDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    const html = document.documentElement;
    
    if (darkModeEnabled) {
        html.setAttribute('data-theme', 'dark');
        document.body.classList.add('bg-dark', 'text-light');
        if (darkModeToggle) {
            darkModeToggle.innerHTML = '<i class="bi bi-sun"></i> Light Mode';
        }
    }
    
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', toggleDarkMode);
    }
}

function toggleDarkMode() {
    const html = document.documentElement;
    const body = document.body;
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    darkModeEnabled = !darkModeEnabled;
    localStorage.setItem('dark_mode', darkModeEnabled);
    
    if (darkModeEnabled) {
        html.setAttribute('data-theme', 'dark');
        body.classList.add('bg-dark', 'text-light');
        darkModeToggle.innerHTML = '<i class="bi bi-sun"></i> Light Mode';
    } else {
        html.setAttribute('data-theme', 'light');
        body.classList.remove('bg-dark', 'text-light');
        darkModeToggle.innerHTML = '<i class="bi bi-moon"></i> Dark Mode';
    }
}

// Progress Tracking Functions
function initializeProgress() {
    const checkboxes = document.querySelectorAll('.module-complete-checkbox');
    checkboxes.forEach(checkbox => {
        const moduleId = parseInt(checkbox.dataset.moduleId);
        if (completedModules.includes(moduleId)) {
            checkbox.checked = true;
        }
        
        checkbox.addEventListener('change', function() {
            toggleModuleCompletion(moduleId);
        });
    });
    
    updateProgressDisplay();
}

function toggleModuleCompletion(moduleId) {
    const index = completedModules.indexOf(moduleId);
    
    if (index === -1) {
        completedModules.push(moduleId);
    } else {
        completedModules.splice(index, 1);
    }
    
    localStorage.setItem('completed_modules', JSON.stringify(completedModules));
    updateProgressDisplay();
    
    // Check if all modules are completed for certificate
    checkCourseCompletion();
}

function updateProgressDisplay() {
    const totalModules = document.querySelectorAll('.module-card').length;
    const completedCount = completedModules.length;
    const percentage = totalModules > 0 ? Math.round((completedCount / totalModules) * 100) : 0;
    
    // Update global progress bar
    const globalProgress = document.getElementById('globalProgress');
    const completedCountSpan = document.getElementById('completedCount');
    const totalCountSpan = document.getElementById('totalCount');
    
    if (globalProgress) {
        globalProgress.style.width = percentage + '%';
        globalProgress.textContent = percentage + '%';
    }
    
    if (completedCountSpan) completedCountSpan.textContent = completedCount;
    if (totalCountSpan) totalCountSpan.textContent = totalModules;
    
    // Update individual module progress bars
    document.querySelectorAll('.module-progress').forEach(progressBar => {
        const moduleId = parseInt(progressBar.dataset.moduleId);
        if (completedModules.includes(moduleId)) {
            progressBar.style.width = '100%';
            progressBar.classList.remove('bg-primary');
            progressBar.classList.add('bg-success');
        } else {
            progressBar.style.width = '0%';
            progressBar.classList.remove('bg-success');
            progressBar.classList.add('bg-primary');
        }
    });
}

function checkCourseCompletion() {
    const totalModules = document.querySelectorAll('.module-card').length;
    const certificateSection = document.getElementById('certificateSection');
    
    if (completedModules.length === totalModules && totalModules > 0 && certificateSection) {
        certificateSection.style.display = 'block';
        // Update certificate link with completion status
        const certLink = certificateSection.querySelector('a[href*="generate_certificate"]');
        if (certLink) {
            certLink.href = `/generate_certificate?completed=${completedModules.join(',')}`;
        }
    } else if (certificateSection) {
        certificateSection.style.display = 'none';
    }
}

function getCompletedModules() {
    return completedModules;
}

// Search Functions
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    const filterButtons = document.querySelectorAll('[data-filter]');
    
    if (searchInput) {
        searchInput.addEventListener('input', performSearch);
    }
    
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Update active filter button
            filterButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Apply filter
            filterModules(this.dataset.filter);
        });
    });
}

function performSearch() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const moduleCards = document.querySelectorAll('.module-card');
    
    moduleCards.forEach(card => {
        const title = card.dataset.title;
        const description = card.querySelector('.card-text')?.textContent.toLowerCase() || '';
        
        if (title.includes(searchTerm) || description.includes(searchTerm)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function filterModules(filter) {
    const moduleCards = document.querySelectorAll('.module-card');
    
    moduleCards.forEach(card => {
        const moduleId = parseInt(card.dataset.moduleId);
        let shouldShow = true;
        
        switch(filter) {
            case 'completed':
                shouldShow = completedModules.includes(moduleId);
                break;
            case 'bookmarked':
                shouldShow = bookmarkedModules.includes(moduleId);
                break;
            case 'all':
            default:
                shouldShow = true;
                break;
        }
        
        card.style.display = shouldShow ? 'block' : 'none';
    });
}

// Bookmark Functions
function initializeBookmarks() {
    const bookmarkButtons = document.querySelectorAll('.bookmark-btn');
    
    bookmarkButtons.forEach(button => {
        const moduleId = parseInt(button.dataset.moduleId);
        
        button.addEventListener('click', function(e) {
            e.preventDefault();
            toggleBookmark(moduleId);
            updateBookmarkButton(button, moduleId);
        });
        
        // Initialize button state
        updateBookmarkButton(button, moduleId);
    });
}

function toggleBookmark(moduleId) {
    const index = bookmarkedModules.indexOf(moduleId);
    
    if (index === -1) {
        bookmarkedModules.push(moduleId);
    } else {
        bookmarkedModules.splice(index, 1);
    }
    
    localStorage.setItem('bookmarked_modules', JSON.stringify(bookmarkedModules));
}

function updateBookmarkButton(button, moduleId) {
    if (bookmarkedModules.includes(moduleId)) {
        button.classList.add('active');
        button.innerHTML = '<i class="bi bi-star-fill"></i> Bookmarked';
    } else {
        button.classList.remove('active');
        button.innerHTML = '<i class="bi bi-star"></i> Bookmark';
    }
}

function getBookmarkedModules() {
    return bookmarkedModules;
}

function updateBookmarkDisplay() {
    const bookmarkButtons = document.querySelectorAll('.bookmark-btn');
    bookmarkButtons.forEach(button => {
        const moduleId = parseInt(button.dataset.moduleId);
        updateBookmarkButton(button, moduleId);
    });
}

// Keyboard Navigation
function initializeKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        // Skip if user is typing in an input field
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        switch(e.key) {
            case '/':
                e.preventDefault();
                const searchInput = document.getElementById('searchInput');
                if (searchInput) {
                    searchInput.focus();
                }
                break;
            case '?':
                e.preventDefault();
                const helpModal = document.getElementById('helpModal');
                if (helpModal) {
                    const modal = new bootstrap.Modal(helpModal);
                    modal.show();
                }
                break;
            case 'ArrowLeft':
                navigateModules(-1);
                break;
            case 'ArrowRight':
                navigateModules(1);
                break;
        }
    });
}

function navigateModules(direction) {
    const currentUrl = window.location.pathname;
    const moduleMatch = currentUrl.match(/\/module\/(\d+)/);
    
    if (moduleMatch) {
        const currentModuleId = parseInt(moduleMatch[1]);
        const newModuleId = currentModuleId + direction;
        
        // Check if new module exists
        if (newModuleId >= 0) {
            window.location.href = `/module/${newModuleId}`;
        }
    } else {
        // On index page, focus first/last module
        const moduleCards = document.querySelectorAll('.module-card:not([style*="display: none"])');
        if (moduleCards.length > 0) {
            const targetCard = direction > 0 ? moduleCards[0] : moduleCards[moduleCards.length - 1];
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

// Utility Functions
function showAlert(message, type = 'info') {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // Find a container to show the alert
    const container = document.querySelector('.container') || document.querySelector('.container-fluid');
    if (container) {
        container.insertAdjacentHTML('afterbegin', alertHtml);
    }
}

function formatDuration(minutes) {
    if (!minutes) return 'N/A';
    
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    
    if (hours > 0) {
        return `${hours}h ${mins}m`;
    } else {
        return `${mins} min`;
    }
}

// Export functions for use in other scripts
window.tutorialPlatform = {
    toggleModuleCompletion,
    toggleBookmark,
    getCompletedModules,
    getBookmarkedModules,
    updateBookmarkDisplay,
    updateProgressDisplay,
    showAlert,
    formatDuration
};