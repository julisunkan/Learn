// Enhanced Service Worker for Tutorial Platform PWA
// Version-based cache management
const CACHE_VERSION = 'v2';
const STATIC_CACHE = `tutorial-platform-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `tutorial-platform-dynamic-${CACHE_VERSION}`;
const API_CACHE = `tutorial-platform-api-${CACHE_VERSION}`;

// Resources to pre-cache (app shell)
const STATIC_RESOURCES = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/js/admin.js',
  '/static/favicon.ico',
  '/manifest.json',
  '/static/pwa-icons/icon-192x192.png',
  '/static/pwa-icons/icon-512x512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js'
];

// Install event - pre-cache static resources
self.addEventListener('install', function(event) {
  console.log('Service Worker: Installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(function(cache) {
        console.log('Service Worker: Pre-caching app shell');
        return cache.addAll(STATIC_RESOURCES);
      })
      .then(function() {
        console.log('Service Worker: Skip waiting for activation');
        return self.skipWaiting(); // Activate immediately
      })
      .catch(function(error) {
        console.error('Service Worker: Pre-caching failed', error);
      })
  );
});

// Activate event - clean up old caches and claim clients
self.addEventListener('activate', function(event) {
  console.log('Service Worker: Activating...');
  event.waitUntil(
    Promise.all([
      // Clean up old caches
      caches.keys().then(function(cacheNames) {
        return Promise.all(
          cacheNames.map(function(cacheName) {
            if (cacheName !== STATIC_CACHE && 
                cacheName !== DYNAMIC_CACHE && 
                cacheName !== API_CACHE) {
              console.log('Service Worker: Clearing old cache', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      }),
      // Take control of all clients immediately
      self.clients.claim()
    ])
  );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', function(event) {
  const request = event.request;
  const url = new URL(request.url);

  // Skip non-GET requests and chrome-extension requests
  if (request.method !== 'GET' || url.protocol === 'chrome-extension:') {
    return;
  }

  event.respondWith(
    handleRequest(request, url)
  );
});

async function handleRequest(request, url) {
  // Strategy 1: Static resources - Cache First
  if (STATIC_RESOURCES.includes(url.pathname) || 
      url.pathname.startsWith('/static/') || 
      url.origin !== self.location.origin) {
    return handleStaticResource(request);
  }
  
  // Strategy 2: API requests - Network First with cache fallback
  if (url.pathname.startsWith('/api/')) {
    return handleApiRequest(request);
  }
  
  // Strategy 3: HTML pages - Network First with offline fallback
  if (request.mode === 'navigate' || 
      request.headers.get('accept')?.includes('text/html')) {
    return handleNavigationRequest(request);
  }
  
  // Default: Network First
  return handleDynamicResource(request);
}

// Cache First strategy for static resources
async function handleStaticResource(request) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.error('Static resource failed:', error);
    return new Response('Resource not available offline', { 
      status: 503, 
      statusText: 'Service Unavailable' 
    });
  }
}

// Network First strategy for API requests
async function handleApiRequest(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('API network failed, trying cache:', request.url);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    return new Response(JSON.stringify({ 
      error: 'Offline - data not available' 
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// Network First strategy for HTML navigation
async function handleNavigationRequest(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('Navigation network failed, trying cache:', request.url);
    
    // Try cached version first
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Fallback to offline page
    return createOfflinePage();
  }
}

// Dynamic resource handling
async function handleDynamicResource(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await caches.match(request);
    return cachedResponse || new Response('Content not available offline', { 
      status: 503 
    });
  }
}

// Create offline fallback page
function createOfflinePage() {
  return new Response(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Offline - Tutorial Platform</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                text-align: center; 
                padding: 2rem; 
                color: #333; 
                background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                min-height: 100vh;
                margin: 0;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .offline-container {
                background: white;
                padding: 3rem;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                max-width: 500px;
            }
            .offline-icon {
                font-size: 4rem;
                margin-bottom: 1rem;
            }
            h1 { color: #007bff; margin-bottom: 1rem; }
            p { color: #666; line-height: 1.6; margin-bottom: 1.5rem; }
            .btn {
                background: #007bff;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 5px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                font-size: 1rem;
            }
            .btn:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="offline-container">
            <div class="offline-icon">📚</div>
            <h1>You're Offline</h1>
            <p>It looks like you're not connected to the internet. Some content may not be available, but you can still access previously visited pages.</p>
            <p>Once your connection is restored, you'll have access to all features.</p>
            <button class="btn" onclick="window.location.reload()">Try Again</button>
        </div>
    </body>
    </html>
  `, {
    headers: { 'Content-Type': 'text/html' },
    status: 200
  });
}

// Handle background sync (future enhancement)
self.addEventListener('sync', function(event) {
  console.log('Service Worker: Background sync triggered');
  if (event.tag === 'progress-sync') {
    event.waitUntil(syncProgress());
  }
});

async function syncProgress() {
  // Future: sync offline progress when online
  console.log('Service Worker: Syncing progress data...');
}

// Handle push notifications (future enhancement)
self.addEventListener('push', function(event) {
  console.log('Service Worker: Push notification received');
  // Future: handle push notifications
});

console.log('Service Worker: Script loaded successfully');