import os
import json
import zipfile
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import blue, black
import markdown
from typing import Optional, Union
from flask import Response
import hashlib
import time
import requests
import urllib.parse
from werkzeug.security import generate_password_hash, check_password_hash
# Import URL content scraping and quiz generation functionality  
from nlp_quiz import WebContentImporter
import logging
import socket
import ipaddress
from PIL import Image
import uuid
import glob

app = Flask(__name__)

# Apply ProxyFix for proper HTTPS/proxy handling in Replit
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Require secure session secret
if not os.environ.get('SESSION_SECRET'):
    raise RuntimeError("SESSION_SECRET environment variable must be set for security")
app.secret_key = os.environ.get('SESSION_SECRET')

# Security configuration for production
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PREFERRED_URL_SCHEME'] = 'https'  # Generate HTTPS URLs
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year

# Configuration
UPLOAD_FOLDER = 'static/resources'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'mp4'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize web content importer for URL scraping and quiz generation
content_importer = WebContentImporter(upload_folder=UPLOAD_FOLDER)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Admin Authentication Functions
def is_admin_authenticated():
    """Check if user is authenticated as admin"""
    return session.get('admin_authenticated', False)

def require_admin_auth():
    """Decorator to require admin authentication - always enforced"""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_admin_authenticated():
                return jsonify({"error": "Admin authentication required"}), 401
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# CSRF Protection
def generate_csrf_token():
    """Generate a CSRF token for the current session"""
    import secrets
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']

def validate_csrf_token():
    """Validate CSRF token from request headers"""
    session_token = session.get('csrf_token')
    request_token = request.headers.get('X-CSRF-Token')

    if not session_token or not request_token:
        return False

    return session_token == request_token

@app.before_request
def check_csrf_on_admin_routes():
    """Apply CSRF protection to all admin POST/PUT/DELETE requests"""
    if request.path.startswith('/admin') and request.method in ['POST', 'PUT', 'DELETE']:
        # Skip CSRF for authentication endpoints and token endpoint
        if request.path in ['/admin/csrf-token', '/admin/login', '/admin/logout']:
            return

        if not validate_csrf_token():
            return jsonify({"error": "CSRF token validation failed"}), 403

# Progress Storage Functions
def load_user_progress():
    """Load user progress from progress.json"""
    try:
        with open('data/progress.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_progress(progress_data):
    """Save user progress to progress.json"""
    os.makedirs('data', exist_ok=True)
    with open('data/progress.json', 'w') as f:
        json.dump(progress_data, f, indent=4)

def get_user_progress(user_fingerprint, module_id):
    """Get progress for a specific user and module"""
    progress_data = load_user_progress()
    user_key = f"{user_fingerprint}_{module_id}"
    return progress_data.get(user_key, {
        'completed': False,
        'quiz_score': None,
        'notes': '',
        'bookmarked': False,
        'last_updated': None
    })

def set_user_progress(user_fingerprint, module_id, progress_update):
    """Update progress for a specific user and module"""
    progress_data = load_user_progress()
    user_key = f"{user_fingerprint}_{module_id}"

    if user_key in progress_data:
        progress_data[user_key].update(progress_update)
    else:
        progress_data[user_key] = {
            'user_fingerprint': user_fingerprint,
            'module_id': module_id,
            'completed': False,
            'quiz_score': None,
            'notes': '',
            'bookmarked': False,
            'last_updated': datetime.now().isoformat()
        }
        progress_data[user_key].update(progress_update)

    progress_data[user_key]['last_updated'] = datetime.now().isoformat()
    save_user_progress(progress_data)
    return progress_data[user_key]

def get_all_user_progress(user_fingerprint):
    """Get all progress for a specific user"""
    progress_data = load_user_progress()
    user_progress = {}

    for key, data in progress_data.items():
        if data.get('user_fingerprint') == user_fingerprint:
            module_id = data.get('module_id')
            if module_id is not None:
                user_progress[str(module_id)] = data

    return user_progress

def generate_user_fingerprint(request):
    """Generate a unique user identifier with UUID cookies as primary method, IP/UA as fallback"""
    import uuid

    # Try to get existing user ID from cookie first  
    user_id = request.cookies.get('user_id')

    if user_id:
        # Validate that it's a proper UUID format
        try:
            uuid.UUID(user_id)
            return user_id
        except ValueError:
            # Invalid UUID format, fall back to generating new one
            pass

    # No valid cookie found, generate new UUID for this user
    new_user_id = str(uuid.uuid4())
    # Store in session so we can set cookie in response
    session['new_user_id'] = new_user_id
    return new_user_id

def set_user_id_cookie(response, user_id):
    """Set the user_id cookie in the response for persistence"""
    response.set_cookie('user_id', user_id, 
                       max_age=10*365*24*60*60,  # 10 years 
                       secure=True,  # HTTPS only in production
                       httponly=True,  # Prevent JavaScript access
                       samesite='Lax')
    return response

@app.after_request
def after_request(response):
    """Set user ID cookie if new user was created during request and add selective cache control headers"""
    if 'new_user_id' in session:
        response = set_user_id_cookie(response, session['new_user_id'])
        # Clear the session flag
        session.pop('new_user_id', None)

    # Set appropriate caching headers based on endpoint type
    if request.endpoint == 'static':
        # Cache static files for a year, except service worker
        if request.path.endswith('/sw.js'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        else:
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif (request.path.startswith('/admin') or 
          request.path.startswith('/api/') or 
          request.endpoint in ['index', 'module_detail']):
        # No cache for dynamic content
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    # Add security headers for HTTPS
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response

def load_config():
    """Load site configuration from config.json and environment"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {
            "site_title": "Tutorial Platform",
            "site_description": "Learn at your own pace",
            "primary_color": "#007bff",
            "secondary_color": "#6c757d",
            "text_color": "#333333",
            "font_size": "16px",
            "font_family": "Arial, sans-serif",
            "enable_passcode": False
        }

    # Override admin passcode with environment variable if available, fallback to hardcoded
    env_passcode = os.environ.get('ADMIN_PASSCODE')
    if env_passcode:
        config['admin_passcode'] = env_passcode
    else:
        # WARNING: Hardcoded passcode is a security risk - visible in source code
        config['admin_passcode'] = 'admin123'

    return config

def save_config(config):
    """Save site configuration to config.json"""
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)

def load_courses():
    """Load courses from data/courses.json"""
    try:
        with open('data/courses.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"modules": []}

def save_courses(courses):
    """Save courses to data/courses.json"""
    os.makedirs('data', exist_ok=True)
    with open('data/courses.json', 'w') as f:
        json.dump(courses, f, indent=4)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Security: Define blocked IP ranges to prevent SSRF attacks
BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),      # localhost
    ipaddress.ip_network('10.0.0.0/8'),       # RFC1918 private
    ipaddress.ip_network('172.16.0.0/12'),    # RFC1918 private
    ipaddress.ip_network('192.168.0.0/16'),   # RFC1918 private
    ipaddress.ip_network('169.254.0.0/16'),   # link-local
    ipaddress.ip_network('224.0.0.0/4'),      # multicast
    ipaddress.ip_network('::1/128'),          # IPv6 localhost
    ipaddress.ip_network('fc00::/7'),         # IPv6 private
    ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
]

def validate_url_security(url):
    """
    Validate URL to prevent SSRF attacks by blocking access to internal/private networks
    """
    parsed = urllib.parse.urlparse(url)

    # Only allow HTTP/HTTPS schemes
    if parsed.scheme not in ['http', 'https']:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    if not parsed.netloc:
        raise ValueError("Invalid URL: no network location")

    # Extract hostname (remove port if present)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: could not extract hostname")

    try:
        # Resolve hostname to IP address
        ip_info = socket.getaddrinfo(hostname, None)
        if not ip_info:
            raise ValueError(f"Could not resolve hostname: {hostname}")

        # Check all resolved IPs
        for ip_data in ip_info:
            ip_str = ip_data[4][0]  # Extract IP string from tuple
            try:
                ip_addr = ipaddress.ip_address(ip_str)

                # Check against blocked networks
                for blocked_network in BLOCKED_NETWORKS:
                    if ip_addr in blocked_network:
                        raise ValueError(f"Access to {ip_str} ({hostname}) is blocked for security reasons")

                logger.debug(f"URL security check passed for {hostname} -> {ip_str}")

            except ValueError as e:
                if "is blocked" in str(e):
                    raise e
                logger.warning(f"Could not parse IP address {ip_str}: {e}")
                continue

    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {hostname}: {e}")
    except Exception as e:
        raise ValueError(f"Security validation failed for {hostname}: {e}")

def save_feedback(module_id, feedback_data):
    """Save feedback to feedback.json"""
    feedback_file = 'data/feedback.json'

    # Load existing feedback
    try:
        with open(feedback_file, 'r') as f:
            feedback = json.load(f)
    except FileNotFoundError:
        feedback = []

    # Add new feedback
    feedback_entry = {
        "module_id": module_id,
        "timestamp": datetime.now().isoformat(),
        **feedback_data
    }
    feedback.append(feedback_entry)

    # Save feedback
    os.makedirs('data', exist_ok=True)
    with open(feedback_file, 'w') as f:
        json.dump(feedback, f, indent=4)

@app.route('/')
def index():
    """Main course index page"""
    config = load_config()
    courses = load_courses()

    # Load user progress based on device fingerprint
    user_fingerprint = generate_user_fingerprint(request)
    user_progress = get_all_user_progress(user_fingerprint)

    return render_template('index.html', config=config, courses=courses, progress=user_progress)

@app.route('/module/<int:module_id>')
def module_detail(module_id):
    """Individual module page"""
    config = load_config()
    courses = load_courses()

    if module_id < 0 or module_id >= len(courses['modules']):
        return "Module not found", 404

    module = courses['modules'][module_id]

    # Load HTML content if exists
    content_file = module.get('content_file', '')
    html_content = ""
    if content_file and os.path.isfile(f"data/modules/{content_file}"):
        content_path = f"data/modules/{content_file}"
        with open(content_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if content_path.endswith('.md'):
                html_content = markdown.markdown(content)
            else:
                html_content = content

        # Sanitize HTML content for security (prevent XSS from imported content)
        try:
            import bleach
            allowed_tags = ['p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'u', 'b', 'i', 
                           'ul', 'ol', 'li', 'a', 'img', 'blockquote', 'pre', 'code', 'div', 'span']
            allowed_attributes = {
                'a': ['href', 'title', 'target'],
                'img': ['src', 'alt', 'title', 'width', 'height', 'style'],
                'div': ['class', 'style'],
                'span': ['class', 'style'],
                'p': ['style'],
                'h1': ['style'], 'h2': ['style'], 'h3': ['style'], 'h4': ['style'], 'h5': ['style'], 'h6': ['style']
            }
            allowed_styles = ['max-width', 'width', 'height', 'margin', 'padding', 'text-align', 'float', 'clear']
            allowed_protocols = ['http', 'https', 'mailto', 'data']

            # Use CSS sanitizer if available
            try:
                from bleach.css_sanitizer import CSSSanitizer
                css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_styles)
                html_content = bleach.clean(html_content, tags=allowed_tags, 
                                          attributes=allowed_attributes, 
                                          protocols=allowed_protocols,
                                          css_sanitizer=css_sanitizer, strip=True)
            except ImportError:
                # Fallback without CSS sanitizer
                safe_attributes = {k: [attr for attr in v if attr != 'style'] 
                                 for k, v in allowed_attributes.items()}
                html_content = bleach.clean(html_content, tags=allowed_tags, 
                                          attributes=safe_attributes, 
                                          protocols=allowed_protocols, strip=True)
        except ImportError:
            # Bleach not available - fallback to basic HTML escaping for safety
            import html
            logger.warning("Bleach not available for HTML sanitization, using basic escaping")
            html_content = f"<div style='background: #fff3cd; padding: 10px; border: 1px solid #ffeaa7; border-radius: 5px;'><strong>Content Warning:</strong> This imported content has been escaped for security. Install 'bleach' package for proper HTML rendering.</div><pre>{html.escape(html_content)}</pre>"

    # Load quiz if exists
    quiz_data = module.get('quiz', {})

    # Load user progress for this module
    user_fingerprint = generate_user_fingerprint(request)
    module_progress = get_user_progress(user_fingerprint, module_id)

    return render_template('course.html', 
                         config=config, 
                         module=module, 
                         module_id=module_id,
                         total_modules=len(courses['modules']),
                         html_content=html_content,
                         quiz=quiz_data,
                         progress=module_progress)

@app.route('/admin')
def admin_dashboard():
    """Admin panel with authentication check - always requires auth"""
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))

    config = load_config()
    courses = load_courses()
    return render_template('admin.html', config=config, courses=courses, mode='dashboard')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    config = load_config()

    if request.method == 'POST':
        passcode = request.form.get('passcode')
        stored_passcode = config.get('admin_passcode')

        if not stored_passcode:
            flash('Admin passcode not configured. Please set ADMIN_PASSCODE environment variable.', 'error')
            return render_template('admin_login.html', config=config)

        if not passcode:
            flash('Please enter the admin passcode', 'error')
            return render_template('admin_login.html', config=config)

        # Check if stored passcode is hashed
        if stored_passcode.startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
            # Use hashed comparison
            if check_password_hash(stored_passcode, passcode):
                session['admin_authenticated'] = True
                flash('Successfully logged in as admin', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin passcode', 'error')
        else:
            # Plain text passcode - authenticate but DO NOT save hash to avoid persistence
            if passcode == stored_passcode:
                session['admin_authenticated'] = True
                flash('Successfully logged in as admin. Consider using hashed passcode in environment.', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin passcode', 'error')

    return render_template('admin_login.html', config=config)

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Admin logout"""
    session.pop('admin_authenticated', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))


@app.route('/admin/csrf-token')
@require_admin_auth()
def get_csrf_token():
    """Get CSRF token for admin session"""
    return jsonify({"csrf_token": generate_csrf_token()})


@app.route('/admin/config', methods=['GET', 'POST'])
@require_admin_auth()
def admin_config():
    """Handle site configuration"""

    if request.method == 'POST':
        config = request.json or {}
        # Never save admin_passcode to file - it should only be in environment
        config_to_save = {k: v for k, v in config.items() if k != 'admin_passcode'}
        save_config(config_to_save)
        return jsonify({"success": True})
    else:
        config = load_config()
        # Never return admin_passcode in API response
        safe_config = {k: v for k, v in config.items() if k != 'admin_passcode'}
        return jsonify(safe_config)

@app.route('/admin/modules', methods=['GET', 'POST', 'PUT', 'DELETE'])  # type: ignore
@require_admin_auth()
def admin_modules():
    """Handle module management"""

    courses = load_courses()

    if request.method == 'GET':
        return jsonify(courses)

    elif request.method == 'POST':
        # Add new module
        module_data = request.json or {}

        # Process uploaded content file for resizing
        if 'content' in module_data and 'content_file' in module_data:
            content_filename = module_data['content_file']
            content_path = f"data/modules/{content_filename}"

            os.makedirs('data/modules', exist_ok=True)
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(module_data['content'])
            
            # Resize images within the content file if it's an HTML/Markdown file
            if content_filename.lower().endswith(('.html', '.htm', '.md')):
                resize_images_in_file(content_path, 500, 500)

            del module_data['content']
        elif 'content' in module_data:
            # If no content_file specified, generate a new one
            content_filename = f"content_{len(courses['modules'])}.html"
            content_path = f"data/modules/{content_filename}"
            os.makedirs('data/modules', exist_ok=True)
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(module_data['content'])
            
            # Resize images within the content file
            if content_filename.lower().endswith(('.html', '.htm', '.md')):
                resize_images_in_file(content_path, 500, 500)

            module_data['content_file'] = content_filename
            del module_data['content']


        courses['modules'].append(module_data)
        save_courses(courses)
        return jsonify({"success": True, "module_id": len(courses['modules']) - 1})

    elif request.method == 'PUT':
        # Update module order and content
        new_order = (request.json or {}).get('modules', [])

        # Get current modules to safely handle content updates
        current_modules = courses['modules']

        # Create a mapping of existing modules by ID for safe content updates
        existing_modules_by_id = {}
        for module in current_modules:
            # Ensure all existing modules have stable IDs
            if 'module_id' not in module:
                import uuid
                module['module_id'] = str(uuid.uuid4())
            existing_modules_by_id[module['module_id']] = module

        # Process each module for content updates using stable IDs
        for module_data in new_order:
            # Ensure new modules have stable IDs  
            if 'module_id' not in module_data:
                import uuid
                module_data['module_id'] = str(uuid.uuid4())

            if 'content' in module_data:
                # Find the corresponding existing module by stable ID - NOT by index
                existing_module = existing_modules_by_id.get(module_data['module_id'])
                existing_content_file = existing_module.get('content_file') if existing_module else None

                if existing_content_file:
                    # Use the existing content file - NEVER trust client-provided paths
                    content_filename = existing_content_file
                else:
                    # Create new content file with UUID for uniqueness and security
                    import uuid
                    content_filename = f"content_{uuid.uuid4().hex[:8]}.html"
                    module_data['content_file'] = content_filename

                # Validate filename for security - only allow safe filenames
                if not content_filename or '/' in content_filename or '\\' in content_filename or '..' in content_filename:
                    logger.error(f"Invalid content filename attempted: {content_filename}")
                    return jsonify({"success": False, "error": "Invalid content file path"}), 400

                content_path = f"data/modules/{content_filename}"

                # Write content to file
                os.makedirs('data/modules', exist_ok=True)
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.write(module_data['content'])
                
                # Resize images within the content file
                if content_filename.lower().endswith(('.html', '.htm', '.md')):
                    resize_images_in_file(content_path, 500, 500)

                # Set the safe content_file reference
                module_data['content_file'] = content_filename
                # Remove content from module data to keep JSON clean
                del module_data['content']

        courses['modules'] = new_order
        save_courses(courses)
        return jsonify({"success": True})

    elif request.method == 'DELETE':
        # Delete module
        module_id = (request.json or {}).get('module_id')
        if module_id is not None and isinstance(module_id, int) and 0 <= module_id < len(courses['modules']):
            # Delete associated files
            module = courses['modules'][module_id]
            if 'content_file' in module:
                content_path = f"data/modules/{module['content_file']}"
                if os.path.exists(content_path):
                    os.remove(content_path)

            courses['modules'].pop(module_id)
            save_courses(courses)
            return jsonify({"success": True})

        return jsonify({"success": False, "error": "Invalid module ID"})

@app.route('/admin/edit_content/<int:module_id>')
@require_admin_auth()
def admin_edit_content(module_id):
    """WYSIWYG editor for module content"""
    config = load_config()
    courses = load_courses()

    if module_id < 0 or module_id >= len(courses['modules']):
        return "Module not found", 404

    module = courses['modules'][module_id]

    # Load content if exists
    content = ""
    if 'content_file' in module:
        content_path = f"data/modules/{module['content_file']}"
        if os.path.exists(content_path):
            with open(content_path, 'r', encoding='utf-8') as f:
                content = f.read()

    return render_template('content_editor.html', 
                         config=config, 
                         module=module, 
                         module_id=module_id,
                         content=content)

@app.route('/admin/get_content/<int:module_id>')
@require_admin_auth()
def get_module_content(module_id):
    """Get module content for editing"""
    courses = load_courses()

    if module_id < 0 or module_id >= len(courses['modules']):
        return jsonify({"success": False, "error": "Module not found"}), 404

    module = courses['modules'][module_id]
    content = ""

    if 'content_file' in module:
        content_path = f"data/modules/{module['content_file']}"
        if os.path.exists(content_path):
            with open(content_path, 'r', encoding='utf-8') as f:
                content = f.read()

    return jsonify({
        "success": True,
        "content": content,
        "module": module
    })

@app.route('/admin/save_content/<int:module_id>', methods=['POST'])
@require_admin_auth()
def save_module_content(module_id):
    """Save edited module content"""
    courses = load_courses()

    if module_id < 0 or module_id >= len(courses['modules']):
        return jsonify({"success": False, "error": "Module not found"}), 404

    data = request.json or {}
    content = data.get('content', '')

    module = courses['modules'][module_id]

    # Ensure content file exists
    if 'content_file' not in module:
        module['content_file'] = f"content_{module_id}.html"

    content_path = f"data/modules/{module['content_file']}"
    os.makedirs('data/modules', exist_ok=True)

    # Save content
    with open(content_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Resize images within the content file
    if module['content_file'].lower().endswith(('.html', '.htm', '.md')):
        resize_images_in_file(content_path, 500, 500)

    # Update module metadata if provided
    if 'title' in data:
        module['title'] = data['title']
    if 'description' in data:
        module['description'] = data['description']

    save_courses(courses)

    return jsonify({"success": True, "message": "Content saved successfully"})

@app.route('/admin/resize_image', methods=['POST'])
@require_admin_auth()
def resize_image():
    """Resize an image to specified dimensions"""
    data = request.json or {}
    image_path = data.get('image_path', '')
    width = data.get('width', 800)
    height = data.get('height', 600)

    if not image_path:
        return jsonify({"success": False, "error": "Image path is required"}), 400

    # Strict validation of dimensions
    try:
        width = int(width)
        height = int(height)
        if width < 10 or width > 2000 or height < 10 or height > 2000:
            return jsonify({"success": False, "error": "Image dimensions must be between 10 and 2000 pixels"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid dimensions"}), 400

    # Security check - ensure image is in static/resources
    if not image_path.startswith('/static/resources/'):
        return jsonify({"success": False, "error": "Invalid image path"}), 400

    # Remove leading slash and get absolute path
    relative_path = image_path[1:]

    # Get the canonical path to prevent directory traversal
    try:
        full_path = os.path.realpath(relative_path)
        resources_dir = os.path.realpath('static/resources')

        # Ensure the resolved path is actually within the resources directory
        if not full_path.startswith(resources_dir + os.sep):
            return jsonify({"success": False, "error": "Access denied: path outside allowed directory"}), 403

    except Exception as e:
        return jsonify({"success": False, "error": "Invalid file path"}), 400

    if not os.path.exists(full_path):
        return jsonify({"success": False, "error": "Image not found"}), 404

    # Validate it's actually an image file
    if not full_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        return jsonify({"success": False, "error": "File is not a valid image"}), 400

    try:
        from PIL import Image
        import uuid

        # Open and validate image
        with Image.open(full_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            resized = img.resize((width, height), Image.Resampling.LANCZOS)

            # Generate secure filename with UUID to prevent conflicts and directory traversal
            original_name = os.path.basename(full_path)
            name_part, ext = os.path.splitext(original_name)
            unique_id = str(uuid.uuid4())[:8]
            new_filename = f"{name_part}_resized_{width}x{height}_{unique_id}{ext}"

            # Ensure new file is saved in resources directory
            new_path = os.path.join('static', 'resources', new_filename)

            # Save resized image
            resized.save(new_path, optimize=True, quality=85)

            # Return web-accessible path
            web_path = f"/static/resources/{new_filename}"

            return jsonify({
                "success": True, 
                "new_path": web_path,
                "message": f"Image resized to {width}x{height}"
            })

    except Exception as e:
        logger.error(f"Error resizing image {full_path}: {str(e)}")
        return jsonify({"success": False, "error": "Error processing image"}), 500

def resize_images_in_file(file_path, target_width, target_height):
    """
    Finds all image tags in an HTML or Markdown file and resizes the images
    to the target dimensions. Updates the image source to point to the resized image.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Could not read file {file_path} for image resizing: {e}")
        return

    import re

    # Regex to find image tags (img src="...") or Markdown images (![alt](src))
    # This regex is simplified and might need adjustment for complex cases
    image_sources = re.findall(r'<img[^>]+src="([^"]+)"', content)
    image_sources.extend(re.findall(r'!\[.*?\]\(([^)]+)\)', content))
    
    resources_dir = os.path.abspath('static/resources')

    for src in image_sources:
        # Clean up src, remove potential query params
        src = src.split('?')[0]
        
        # Ensure the image is in the /static/resources folder
        if src.startswith('/static/resources/'):
            image_path_relative = src[1:] # Remove leading slash
            
            try:
                full_image_path = os.path.abspath(image_path_relative)

                # Security check: Ensure the image path is within the resources directory
                if not full_image_path.startswith(resources_dir + os.sep):
                    logger.warning(f"Skipping resize for image outside resources directory: {src}")
                    continue

                if not os.path.exists(full_image_path):
                    logger.warning(f"Image not found for resizing: {full_image_path}")
                    continue

                # Resize the image
                resized_path = resize_single_image(full_image_path, target_width, target_height)

                if resized_path:
                    # Update the content with the new path
                    new_src = resized_path.replace('\\', '/') # Use forward slashes for web paths
                    # Replace in both HTML and Markdown formats
                    content = content.replace(f'src="{src}"', f'src="{new_src}"')
                    content = content.replace(f'src="{src.split("/")[-1]}"', f'src="{new_src}"') # Handle relative paths if they appear like that
                    content = content.replace(f'![^)]+]({src})', f'![^)]+]({new_src})')

            except Exception as e:
                logger.error(f"Error processing image {src}: {e}")
                continue

    # Save the modified content back to the file
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Resized images in {file_path} and updated content.")
    except Exception as e:
        logger.error(f"Could not save modified content for {file_path}: {e}")


def resize_single_image(image_path, width, height):
    """
    Resizes a single image to the specified width and height, saves it with a new name,
    and returns the web-accessible path to the resized image.
    """
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            resized = img.resize((width, height), Image.Resampling.LANCZOS)

            original_name = os.path.basename(image_path)
            name_part, ext = os.path.splitext(original_name)
            unique_id = str(uuid.uuid4())[:8]
            new_filename = f"{name_part}_resized_{width}x{height}_{unique_id}{ext}"

            new_path = os.path.join('static', 'resources', new_filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(new_path), exist_ok=True)

            resized.save(new_path, optimize=True, quality=85)
            
            return f"/static/resources/{new_filename}"

    except Exception as e:
        logger.error(f"Failed to resize image {image_path}: {e}")
        return None

@app.route('/admin/upload_resource', methods=['POST'])
@require_admin_auth()
def upload_resource():
    """Handle file uploads for resources"""

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file selected"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    if file and allowed_file(file.filename):
        if file.filename:
            filename = secure_filename(file.filename)
        else:
            return jsonify({"success": False, "error": "Invalid filename"})
        # Add timestamp to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        filename = timestamp + filename
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Resize uploaded image if it's an image file
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            resized_path = resize_single_image(file_path, 500, 500)
            if resized_path:
                # Return the path to the resized image
                return jsonify({"success": True, "filename": os.path.basename(resized_path), "url": resized_path})
            else:
                # If resizing failed, return the original path but log the error
                return jsonify({"success": True, "filename": filename, "url": f"/static/resources/{filename}", "warning": "Image resizing failed."})

        return jsonify({"success": True, "filename": filename, "url": f"/static/resources/{filename}"})

    return jsonify({"success": False, "error": "Invalid file type"})

@app.route('/admin/upload_pwa_icon', methods=['POST'])
@require_admin_auth()
def upload_pwa_icon():
    """Handle PWA icon upload and generate all required sizes"""

    if 'icon' not in request.files:
        return jsonify({"success": False, "error": "No icon file selected"})

    file = request.files['icon']
    if file.filename == '':
        return jsonify({"success": False, "error": "No icon file selected"})

    if not file or not file.filename or not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify({"success": False, "error": "Please upload a PNG or JPEG image"})

    try:
        from PIL import Image

        # Open and validate the uploaded image
        image = Image.open(file.stream)

        # Convert to RGBA for transparency support
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # PWA icon sizes according to guidelines
        pwa_sizes = [192, 512]

        # Ensure PWA icons directory exists
        pwa_dir = 'static/pwa-icons'
        os.makedirs(pwa_dir, exist_ok=True)

        generated_icons = []

        for size in pwa_sizes:
            # Generate regular icon
            regular_icon = image.resize((size, size), Image.Resampling.LANCZOS)
            regular_filename = f"icon-{size}x{size}.png"
            regular_path = os.path.join(pwa_dir, regular_filename)
            regular_icon.save(regular_path, 'PNG', optimize=True)
            generated_icons.append(f"Regular {size}x{size}")

            # Generate maskable icon (with safe zone - scale down to 80% and center)
            maskable_icon = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            safe_size = int(size * 0.8)  # 80% for safe zone
            safe_icon = image.resize((safe_size, safe_size), Image.Resampling.LANCZOS)

            # Center the safe icon in the maskable canvas
            offset = (size - safe_size) // 2
            maskable_icon.paste(safe_icon, (offset, offset))

            maskable_filename = f"icon-{size}x{size}-maskable.png"
            maskable_path = os.path.join(pwa_dir, maskable_filename)
            maskable_icon.save(maskable_path, 'PNG', optimize=True)
            generated_icons.append(f"Maskable {size}x{size}")

        return jsonify({
            "success": True, 
            "message": f"Generated {len(generated_icons)} PWA icons successfully",
            "icons": generated_icons
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Error processing image: {str(e)}"})

@app.route('/data/modules/<filename>')
def serve_module_content(filename):
    """Serve module content files for admin editing"""
    # Security check - only allow specific file extensions
    if not filename.endswith(('.html', '.md', '.txt')):
        return "File type not allowed", 403

    file_path = os.path.join('data', 'modules', filename)
    if not os.path.isfile(file_path):
        return "File not found", 404

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error reading file: {str(e)}", 500

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    """Handle feedback submission"""
    data = request.json or {}
    module_id = data.get('module_id')
    feedback_data = {
        "rating": data.get('rating'),
        "comment": data.get('comment'),
        "user_agent": request.headers.get('User-Agent', ''),
        "ip_address": request.remote_addr
    }

    save_feedback(module_id, feedback_data)
    return jsonify({"success": True})

@app.route('/api/feedback', methods=['GET'])
def get_feedback():
    """Get all feedback data for admin panel"""
    try:
        with open('data/feedback.json', 'r') as f:
            feedback_data = json.load(f)
        return jsonify(feedback_data)
    except FileNotFoundError:
        return jsonify([])

# Progress Tracking API Endpoints
@app.route('/api/progress', methods=['GET'])
def get_progress():
    """Get all progress for the current user based on device fingerprint"""
    user_fingerprint = generate_user_fingerprint(request)
    progress = get_all_user_progress(user_fingerprint)
    return jsonify(progress)

@app.route('/api/progress', methods=['POST'])
def update_progress():
    """Update progress for a specific module"""
    data = request.json or {}
    module_id = data.get('module_id')
    if module_id is None:
        return jsonify({"success": False, "error": "module_id is required"}), 400

    user_fingerprint = generate_user_fingerprint(request)

    # Extract progress updates from request
    progress_update = {}
    if 'completed' in data:
        progress_update['completed'] = data['completed']
    if 'notes' in data:
        progress_update['notes'] = data['notes']
    if 'bookmarked' in data:
        progress_update['bookmarked'] = data['bookmarked']
    if 'quiz_score' in data:
        progress_update['quiz_score'] = data['quiz_score']

    # Update progress
    updated_progress = set_user_progress(user_fingerprint, module_id, progress_update)
    return jsonify({"success": True, "progress": updated_progress})

@app.route('/api/quiz_result', methods=['POST'])
def save_quiz_result():
    """Save quiz results for a module"""
    data = request.json or {}
    module_id = data.get('module_id')
    score = data.get('score')

    if module_id is None or score is None:
        return jsonify({"success": False, "error": "module_id and score are required"}), 400

    user_fingerprint = generate_user_fingerprint(request)

    # Update progress with quiz score
    progress_update = {'quiz_score': score}
    updated_progress = set_user_progress(user_fingerprint, module_id, progress_update)
    return jsonify({"success": True, "progress": updated_progress})

def secure_fetch_with_redirect_validation(url, max_redirects=5, max_size=50*1024*1024, timeout=30):
    """
    Securely fetch URL with manual redirect handling and validation of each redirect target
    """
    current_url = url
    redirect_count = 0

    while redirect_count <= max_redirects:
        # Validate current URL for security
        validate_url_security(current_url)

        # Fetch without following redirects, disable proxy usage
        response = requests.get(
            current_url, 
            timeout=timeout, 
            allow_redirects=False, 
            stream=True,
            proxies={}        # Explicitly disable proxies
        )

        # If not a redirect, return the response
        if response.status_code not in [301, 302, 303, 307, 308]:
            response.raise_for_status()
            return response

        # Handle redirect - validate the new location
        location = response.headers.get('Location')
        if not location:
            raise ValueError("Redirect response missing Location header")

        # Convert relative URLs to absolute
        if location.startswith('/'):
            parsed_current = urllib.parse.urlparse(current_url)
            current_url = f"{parsed_current.scheme}://{parsed_current.netloc}{location}"
        elif not location.startswith(('http://', 'https://')):
            # Relative path - join with current URL
            current_url = urllib.parse.urljoin(current_url, location)
        else:
            current_url = location

        redirect_count += 1

        # Log redirect for security monitoring
        logger.warning(f"Following redirect {redirect_count}/{max_redirects}: {location}")

    raise ValueError(f"Too many redirects (max {max_redirects})")

@app.route('/download_resource')
def download_resource():
    """
    Disabled for security reasons - SSRF vulnerability risk

    This endpoint has been disabled to prevent Server-Side Request Forgery (SSRF) attacks.
    For security, external resource downloads should be handled client-side or through
    a dedicated, isolated service with proper IP pinning and allowlist controls.
    """
    logger.warning("Attempt to access disabled download_resource endpoint")
    return jsonify({
        "error": "Resource download endpoint disabled for security",
        "message": "This feature has been disabled to prevent SSRF attacks. Please download resources directly from your browser."
    }), 403

@app.route('/generate_certificate')
def generate_certificate():
    """Generate completion certificate"""
    # Verify completion status server-side
    courses = load_courses()
    total_modules = len(courses['modules'])

    # Verify completion status using actual server-stored progress
    user_fingerprint = generate_user_fingerprint(request)
    user_progress = get_all_user_progress(user_fingerprint)

    # Count completed modules from server data
    completed_modules = []
    for module_id in range(total_modules):
        module_progress = user_progress.get(str(module_id), {})
        if module_progress.get('completed', False):
            completed_modules.append(module_id)

    # Verify all modules are actually completed on server
    if len(completed_modules) != total_modules:
        missing_count = total_modules - len(completed_modules)
        return f"Please complete all {total_modules} modules before generating certificate. You have completed {len(completed_modules)}, missing {missing_count} modules.", 400

    # Create a PDF certificate
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Certificate content
    config = load_config()
    site_title = config.get('site_title', 'Tutorial Platform')

    p.setFont("Helvetica-Bold", 24)
    # Certificate content - using drawString with centered positioning
    width = 612  # letter width
    p.drawString(width/2 - 100, 700, "Certificate of Completion")

    p.setFont("Helvetica", 16)
    p.drawString(width/2 - 80, 650, "This certifies that")

    p.setFont("Helvetica-Bold", 20)
    p.drawString(width/2 - 40, 600, "Student")

    p.setFont("Helvetica", 16)
    p.drawString(width/2 - 120, 550, "has successfully completed the course")

    p.setFont("Helvetica-Bold", 18)
    p.drawString(width/2 - len(site_title)*5, 500, site_title)

    p.setFont("Helvetica", 12)
    date_str = f"Date: {datetime.now().strftime('%B %d, %Y')}"
    p.drawString(width/2 - len(date_str)*3, 450, date_str)

    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, 
                    download_name=f"certificate_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mimetype='application/pdf')

@app.route('/admin/export_course')
@require_admin_auth()
def export_course():
    """Export entire course as ZIP file"""

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add sanitized config file (without secrets)
        config = load_config()
        safe_config = {k: v for k, v in config.items() if k != 'admin_passcode'}
        config_data = json.dumps(safe_config, indent=4)
        zip_file.writestr('config.json', config_data)

        # Add courses data
        zip_file.write('data/courses.json', 'data/courses.json')

        # Add module files
        if os.path.exists('data/modules'):
            for filename in os.listdir('data/modules'):
                file_path = os.path.join('data/modules', filename)
                if os.path.isfile(file_path):
                    zip_file.write(file_path, f'data/modules/{filename}')

        # Add resources
        if os.path.exists('static/resources'):
            for filename in os.listdir('static/resources'):
                file_path = os.path.join('static/resources', filename)
                if os.path.isfile(file_path):
                    zip_file.write(file_path, f'static/resources/{filename}')

    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                    download_name=f"course_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mimetype='application/zip')

@app.route('/admin/import_course', methods=['POST'])
@require_admin_auth()
def import_course():
    """Import course from ZIP file"""

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file selected"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    if file and file.filename and file.filename.lower().endswith('.zip'):
        try:
            # Create a temporary file to work with ZipFile
            import tempfile
            with tempfile.NamedTemporaryFile() as temp_file:
                file.save(temp_file.name)
                with zipfile.ZipFile(temp_file.name, 'r') as zip_file:
                    # Safe extraction with strict path validation
                    base_dir = os.path.abspath('.')
                    allowed_files = {
                        'config.json': base_dir,
                        'data/courses.json': base_dir
                    }
                    allowed_dirs = {
                        'data/modules/': os.path.join(base_dir, 'data', 'modules'),
                        'static/resources/': os.path.join(base_dir, 'static', 'resources')
                    }

                    for member in zip_file.infolist():
                        # Skip directories and files with .. segments
                        if member.is_dir() or '..' in member.filename:
                            continue

                        # Normalize member filename
                        member_name = member.filename.replace('\\', '/')

                        # Check allowed files
                        dest_path = None
                        target_dir = None

                        if member_name in allowed_files:
                            target_dir = allowed_files[member_name]
                            dest_path = os.path.join(target_dir, os.path.basename(member_name))
                        else:
                            # Check allowed directories
                            for prefix, prefix_dir in allowed_dirs.items():
                                if member_name.startswith(prefix):
                                    # Extract relative path after prefix
                                    rel_path = member_name[len(prefix):]
                                    if '/' not in rel_path:  # Only allow files directly in the target dir
                                        dest_path = os.path.join(prefix_dir, secure_filename(rel_path))
                                        target_dir = prefix_dir
                                        break

                            if not target_dir or dest_path is None:
                                continue

                        # Final security check - ensure dest is within target
                        if dest_path is not None and target_dir is not None:
                            dest_path = os.path.abspath(dest_path)
                            if not dest_path.startswith(os.path.abspath(target_dir) + os.sep):
                                continue
                        else:
                            continue

                        # Create directory and extract
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zip_file.open(member) as source, open(dest_path, 'wb') as target:
                            target.write(source.read())
                            
                        # If it's an image in resources, resize it
                        if member_name.startswith('static/resources/') and member_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                            resize_images_in_file(dest_path, 500, 500)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    return jsonify({"success": False, "error": "Invalid file type"})

@app.route('/admin/import_url', methods=['POST'])
@require_admin_auth()
def admin_import_url():
    """Import content from URL with automatic quiz generation"""

    try:
        data = request.json or {}
        url = data.get('url', '').strip()
        title = data.get('title', '').strip()
        include_images = data.get('include_images', True)
        generate_quiz = data.get('generate_quiz', True)
        num_mcq = min(10, max(1, data.get('num_mcq', 5)))
        num_tf = min(10, max(1, data.get('num_tf', 3)))

        if not url:
            return jsonify({"success": False, "error": "URL is required"}), 400

        # Import content from URL
        scraped_content = content_importer.scrape_url_content(url, include_images)

        # Use provided title or extracted title
        module_title = title or scraped_content.get('title', f'Content from {url}')

        # Generate quiz if requested
        quiz_data = {}
        if generate_quiz and scraped_content.get('text'):
            try:
                quiz_data = content_importer.generate_quiz(
                    scraped_content['text'], 
                    num_mcq=num_mcq, 
                    num_tf=num_tf
                )
            except Exception as e:
                logger.warning(f"Quiz generation failed: {str(e)}")
                quiz_data = {"questions": []}

        # Load courses and create new module
        courses = load_courses()
        module_id = len(courses['modules'])

        # Save content to file
        content_filename = f"content_{module_id}.html"
        content_path = f"data/modules/{content_filename}"

        os.makedirs('data/modules', exist_ok=True)
        with open(content_path, 'w', encoding='utf-8') as f:
            f.write(scraped_content['html'])
        
        # Resize images within the content file
        if content_filename.lower().endswith(('.html', '.htm', '.md')):
            resize_images_in_file(content_path, 500, 500)

        # Create excerpt from text for description
        text = scraped_content.get('text', '')
        description = text[:200] + '...' if len(text) > 200 else text

        # Create new module
        new_module = {
            "title": module_title,
            "description": description,
            "content_file": content_filename,
            "duration": "15 min",
            "source_url": url,
            "imported_images": scraped_content.get('images', [])
        }

        # Add quiz if generated
        if quiz_data.get('questions'):
            new_module['quiz'] = quiz_data

        # Add module to courses
        courses['modules'].append(new_module)
        save_courses(courses)

        return jsonify({
            "success": True,
            "module_id": module_id,
            "title": module_title,
            "images_imported": len(scraped_content.get('images', [])),
            "quiz_questions": len(quiz_data.get('questions', [])),
            "content_length": len(text)
        })

    except Exception as e:
        logger.error(f"URL import error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/generate_quiz', methods=['POST'])
@require_admin_auth()
def admin_generate_quiz():
    """Generate quiz from existing content or provided text"""

    try:
        data = request.json or {}
        module_id = data.get('module_id')
        provided_text = data.get('text', '').strip()
        num_mcq = min(10, max(1, data.get('num_mcq', 5)))
        num_tf = min(10, max(1, data.get('num_tf', 3)))
        persist = data.get('persist', False)

        # Get text content
        text_content = provided_text

        if not text_content and module_id is not None:
            # Load text from existing module
            courses = load_courses()
            if 0 <= module_id < len(courses['modules']):
                module = courses['modules'][module_id]
                content_file = module.get('content_file')
                if content_file:
                    content_path = f"data/modules/{content_file}"
                    if os.path.exists(content_path):
                        with open(content_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                        # Extract text from HTML
                        import re
                        text_content = re.sub('<[^<]+?>', '', html_content)

        if not text_content:
            return jsonify({"success": False, "error": "No text content available for quiz generation"}), 400

        # Generate quiz
        quiz_data = content_importer.generate_quiz(text_content, num_mcq=num_mcq, num_tf=num_tf)

        # Persist quiz to module if requested
        if persist and module_id is not None:
            courses = load_courses()
            if 0 <= module_id < len(courses['modules']):
                courses['modules'][module_id]['quiz'] = quiz_data
                save_courses(courses)

        return jsonify({
            "success": True,
            "quiz": quiz_data,
            "num_questions": len(quiz_data.get('questions', []))
        })

    except Exception as e:
        logger.error(f"Quiz generation error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/manifest.json')
def manifest():
    """Generate PWA manifest.json dynamically"""
    config = load_config()

    # Default PWA icons if none uploaded
    icons = []

    # Check for uploaded PWA icons
    pwa_icons_dir = 'static/pwa-icons'
    if os.path.exists(pwa_icons_dir):
        for size in ['72', '96', '128', '144', '152', '192', '384', '512']:
            icon_file = f'icon-{size}x{size}.png'
            maskable_file = f'icon-{size}x{size}-maskable.png'

            if os.path.exists(os.path.join(pwa_icons_dir, icon_file)):
                icons.append({
                    "src": f"/static/pwa-icons/{icon_file}",
                    "sizes": f"{size}x{size}",
                    "type": "image/png"
                })

            if os.path.exists(os.path.join(pwa_icons_dir, maskable_file)):
                icons.append({
                    "src": f"/static/pwa-icons/{maskable_file}",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": "maskable"
                })

    # Fallback to favicon if no PWA icons
    if not icons:
        icons.append({
            "src": "/static/favicon.ico",
            "sizes": "64x64 32x32 24x24 16x16",
            "type": "image/x-icon"
        })

    manifest_data = {
        "name": config.get('site_title', 'Tutorial Platform'),
        "short_name": config.get('site_title', 'Tutorial Platform')[:12],
        "description": config.get('site_description', 'Learn at your own pace'),
        "start_url": "/",
        "display": "standalone",
        "background_color": config.get('primary_color', '#007bff'),
        "theme_color": config.get('primary_color', '#007bff'),
        "icons": icons,
        "orientation": "portrait-primary",
        "categories": ["education", "productivity"]
    }

    response = jsonify(manifest_data)
    response.headers['Content-Type'] = 'application/manifest+json'
    return response

@app.route('/sw.js')
def service_worker():
    """Serve service worker from root path for proper scope"""
    response = app.send_static_file('sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache'
    return response


if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('data/modules', exist_ok=True)
    os.makedirs('static/resources', exist_ok=True)
    os.makedirs('static/pwa-icons', exist_ok=True)
    os.makedirs('templates', exist_ok=True)

    # Initialize data directories and resize existing images in resources
    print("Data directories initialized successfully.")
    
    # Resize all existing images in the /resources folder
    resource_images = glob.glob('static/resources/*.*')
    for img_path in resource_images:
        if img_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            resize_single_image(img_path, 500, 500)
            logger.info(f"Resized existing image: {img_path}")

    # Only enable debug in development
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)