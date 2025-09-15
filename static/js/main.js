// Main JavaScript for Tutorial Platform

// Global variables for user progress
let completedModules = [];
let bookmarkedModules = [];
let userProgress = {};

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Initialize application by loading progress from server
async function initializeApp() {
    try {
        await loadProgressFromServer();
        initializeProgress();
        initializeSearch();
        initializeKeyboardNavigation();
        initializeBookmarks();
    } catch (error) {
        console.error('Failed to initialize app:', error);
        // Fall back to localStorage if server fails
        loadProgressFromLocalStorage();
        initializeProgress();
        initializeSearch();
        initializeKeyboardNavigation();
        initializeBookmarks();
    }
}

// Load progress from server
async function loadProgressFromServer() {
    const response = await fetch('/api/progress');
    if (!response.ok) {
        throw new Error('Failed to load progress from server');
    }

    userProgress = await response.json();

    // Extract completed and bookmarked modules
    completedModules = [];
    bookmarkedModules = [];

    Object.values(userProgress).forEach(progress => {
        const moduleId = progress.module_id;
        if (progress.completed) {
            completedModules.push(moduleId);
        }
        if (progress.bookmarked) {
            bookmarkedModules.push(moduleId);
        }
    });
}

// Fallback to localStorage for backward compatibility
function loadProgressFromLocalStorage() {
    completedModules = JSON.parse(localStorage.getItem('completed_modules') || '[]');
    bookmarkedModules = JSON.parse(localStorage.getItem('bookmarked_modules') || '[]');
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

async function toggleModuleCompletion(moduleId) {
    const index = completedModules.indexOf(moduleId);
    const completed = index === -1;

    try {
        // Update on server first
        const response = await fetch('/api/progress', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                module_id: moduleId,
                completed: completed
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update progress on server');
        }

        // Update local state if server update succeeded
        if (completed) {
            completedModules.push(moduleId);
        } else {
            completedModules.splice(index, 1);
        }

        // Also update localStorage as fallback
        localStorage.setItem('completed_modules', JSON.stringify(completedModules));

        updateProgressDisplay();
        checkCourseCompletion();

    } catch (error) {
        console.error('Error updating module completion:', error);
        // Revert checkbox state if update failed
        const checkbox = document.querySelector(`[data-module-id=\"${moduleId}\"]`);
        if (checkbox) {
            checkbox.checked = !completed;
        }
    }
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

async function toggleBookmark(moduleId) {
    const index = bookmarkedModules.indexOf(moduleId);
    const bookmarked = index === -1;

    try {
        // Update on server first
        const response = await fetch('/api/progress', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                module_id: moduleId,
                bookmarked: bookmarked
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update bookmark on server');
        }

        // Update local state if server update succeeded
        if (bookmarked) {
            bookmarkedModules.push(moduleId);
        } else {
            bookmarkedModules.splice(index, 1);
        }

        // Also update localStorage as fallback
        localStorage.setItem('bookmarked_modules', JSON.stringify(bookmarkedModules));

    } catch (error) {
        console.error('Error updating bookmark:', error);
    }
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
    // Remove any existing alerts first
    const existingAlerts = document.querySelectorAll('.main-alert');
    existingAlerts.forEach(alert => alert.remove());

    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show main-alert mb-3" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    // Find a container to show the alert
    const container = document.querySelector('.container') || document.querySelector('.container-fluid');
    if (container) {
        container.insertAdjacentHTML('afterbegin', alertHtml);

        // Scroll to the alert
        const newAlert = container.querySelector('.main-alert');
        if (newAlert) {
            newAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    // Auto-remove after 5 seconds
    setTimeout(() => {
        const alert = document.querySelector('.main-alert');
        if (alert) {
            alert.remove();
        }
    }, 5000);
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

// Cache Management Functions
async function clearAppCache() {
    try {
        // Clear browser cache
        if ('caches' in window) {
            const cacheNames = await caches.keys();
            console.log('Found caches to clear:', cacheNames);

            const deletePromises = cacheNames.map(cacheName => {
                console.log('Deleting cache:', cacheName);
                return caches.delete(cacheName);
            });

            await Promise.all(deletePromises);
            console.log('Browser caches cleared successfully');
        }

        // Clear localStorage
        localStorage.clear();
        console.log('LocalStorage cleared');

        // Clear sessionStorage
        sessionStorage.clear();
        console.log('SessionStorage cleared');

        // Clear service worker cache via message
        if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            return new Promise((resolve, reject) => {
                const messageChannel = new MessageChannel();

                messageChannel.port1.onmessage = function(event) {
                    if (event.data.success) {
                        console.log('Service worker caches cleared successfully');
                        resolve(true);
                    } else {
                        console.error('Service worker cache clearing failed:', event.data.error);
                        reject(new Error(event.data.error));
                    }
                };

                navigator.serviceWorker.controller.postMessage({
                    type: 'CLEAR_CACHE'
                }, [messageChannel.port2]);
            });
        }

        return true;
    } catch (error) {
        console.error('Error clearing cache:', error);
        throw error;
    }
}

async function hardRefresh() {
    try {
        await clearAppCache();

        // Force reload without cache
        if ('serviceWorker' in navigator) {
            // Unregister service worker for complete refresh
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (let registration of registrations) {
                await registration.unregister();
                console.log('Service worker unregistered');
            }
        }

        // Hard reload the page
        window.location.reload(true);
    } catch (error) {
        console.error('Error during hard refresh:', error);
        // Fallback to regular reload
        window.location.reload();
    }
}

// PWA Install functionality
let deferredPrompt;
let installButton;

// Toast notification function
function showToast(message, type = 'success') {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'error' ? 'bg-danger' : 'bg-success';

    const toastHTML = `
        <div id="${toastId}" class="toast ${bgClass} text-white" role="alert">
            <div class="toast-body">
                <i class="bi bi-${type === 'error' ? 'exclamation-triangle' : 'check-circle'}"></i>
                ${message}
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);

    // Show toast and auto-hide
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializePWA();
    loadProgress();
    initializeModuleCard();
});

// Export functions for use in other scripts
window.tutorialPlatform = {
    toggleModuleCompletion,
    toggleBookmark,
    getCompletedModules,
    getBookmarkedModules,
    updateBookmarkDisplay,
    updateProgressDisplay,
    showAlert,
    formatDuration,
    clearAppCache,
    hardRefresh,
    showToast
};