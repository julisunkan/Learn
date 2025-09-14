import os
import json
import zipfile
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
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

app = Flask(__name__)
# Require secure session secret
if not os.environ.get('SESSION_SECRET'):
    raise RuntimeError("SESSION_SECRET environment variable must be set for security")
app.secret_key = os.environ.get('SESSION_SECRET')

# Configuration
UPLOAD_FOLDER = 'static/resources'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'mp4'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
                       secure=False,  # Set to True in production with HTTPS
                       httponly=True,  # Prevent JavaScript access
                       samesite='Lax')
    return response

@app.after_request
def after_request(response):
    """Set user ID cookie if new user was created during request"""
    if 'new_user_id' in session:
        response = set_user_id_cookie(response, session['new_user_id'])
        # Clear the session flag
        session.pop('new_user_id', None)
    return response

def load_config():
    """Load site configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "site_title": "Tutorial Platform",
            "site_description": "Learn at your own pace",
            "primary_color": "#007bff",
            "secondary_color": "#6c757d",
            "text_color": "#333333",
            "font_size": "16px",
            "font_family": "Arial, sans-serif",
            "admin_passcode": "admin123",
            "enable_passcode": True
        }

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
def admin_login():
    """Admin login page"""
    config = load_config()
    return render_template('admin.html', config=config, mode='login')

@app.route('/admin/dashboard')
def admin_dashboard():
    """Main admin dashboard"""
    if not session.get('admin_authenticated', False):
        return redirect(url_for('admin_login'))
    
    config = load_config()
    courses = load_courses()
    return render_template('admin.html', config=config, courses=courses, mode='dashboard')

@app.route('/admin/verify_passcode', methods=['POST'])
def verify_passcode():
    """Verify admin passcode"""
    config = load_config()
    entered_passcode = (request.json or {}).get('passcode')
    
    if not config.get('enable_passcode', True) or entered_passcode == config.get('admin_passcode'):
        session['admin_authenticated'] = True
        return jsonify({"success": True})
    else:
        return jsonify({"success": False})

@app.route('/admin/config', methods=['GET', 'POST'])
def admin_config():
    """Handle site configuration"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401  # type: ignore
    
    if request.method == 'POST':
        config = request.json or {}
        save_config(config)
        return jsonify({"success": True})
    else:
        return jsonify(load_config())

@app.route('/admin/modules', methods=['GET', 'POST', 'PUT', 'DELETE'])  # type: ignore
def admin_modules():
    """Handle module management"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401  # type: ignore
    
    courses = load_courses()
    
    if request.method == 'GET':
        return jsonify(courses)
    
    elif request.method == 'POST':
        # Add new module
        module_data = request.json or {}
        
        # Generate unique filename for content
        if 'content' in module_data:
            content_filename = f"content_{len(courses['modules'])}.html"
            content_path = f"data/modules/{content_filename}"
            
            os.makedirs('data/modules', exist_ok=True)
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(module_data['content'])
            
            module_data['content_file'] = content_filename
            del module_data['content']
        
        courses['modules'].append(module_data)
        save_courses(courses)
        return jsonify({"success": True, "module_id": len(courses['modules']) - 1})
    
    elif request.method == 'PUT':
        # Update module order
        new_order = (request.json or {}).get('modules', [])
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

@app.route('/admin/upload_resource', methods=['POST'])
def upload_resource():
    """Handle file uploads for resources"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401  # type: ignore
    
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
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        return jsonify({"success": True, "filename": filename, "url": f"/static/resources/{filename}"})
    
    return jsonify({"success": False, "error": "Invalid file type"})

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
def export_course():
    """Export entire course as ZIP file"""
    if not session.get('admin_authenticated', False):
        return redirect(url_for('admin_login'))
    
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add config file
        zip_file.write('config.json', 'config.json')
        
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
def import_course():
    """Import course from ZIP file"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401  # type: ignore
    
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
            
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    return jsonify({"success": False, "error": "Invalid file type"})

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

@app.route('/admin/upload_pwa_icon', methods=['POST'])
def upload_pwa_icon():
    """Handle PWA icon uploads"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401  # type: ignore
    
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file selected"})
    
    file = request.files['file']
    icon_type = request.form.get('icon_type', 'regular')  # 'regular' or 'maskable'
    icon_size = request.form.get('icon_size', '192')
    
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})
    
    if file and file.filename and file.filename.lower().endswith('.png'):
        os.makedirs('static/pwa-icons', exist_ok=True)
        
        suffix = '-maskable' if icon_type == 'maskable' else ''
        filename = f'icon-{icon_size}x{icon_size}{suffix}.png'
        file_path = os.path.join('static/pwa-icons', filename)
        
        file.save(file_path)
        
        return jsonify({
            "success": True, 
            "filename": filename,
            "url": f"/static/pwa-icons/{filename}"
        })
    
    return jsonify({"success": False, "error": "Only PNG files are allowed for PWA icons"})

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('data/modules', exist_ok=True)
    os.makedirs('static/resources', exist_ok=True)
    os.makedirs('static/pwa-icons', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Initialize data directories
    print("Data directories initialized successfully.")
    
    # Only enable debug in development
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)