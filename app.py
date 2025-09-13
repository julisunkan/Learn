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
from typing import Optional
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
    \"\"\"Load user progress from progress.json\"\"\"
    try:
        with open('data/progress.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_progress(progress_data):
    \"\"\"Save user progress to progress.json\"\"\"
    os.makedirs('data', exist_ok=True)
    with open('data/progress.json', 'w') as f:
        json.dump(progress_data, f, indent=4)

def get_user_progress(user_fingerprint, module_id):
    \"\"\"Get progress for a specific user and module\"\"\"
    progress_data = load_user_progress()
    user_key = f\"{user_fingerprint}_{module_id}\"
    return progress_data.get(user_key, {
        'completed': False,
        'quiz_score': None,
        'notes': '',
        'bookmarked': False,
        'last_updated': None
    })

def set_user_progress(user_fingerprint, module_id, progress_update):
    \"\"\"Update progress for a specific user and module\"\"\"
    progress_data = load_user_progress()
    user_key = f\"{user_fingerprint}_{module_id}\"
    
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
    \"\"\"Get all progress for a specific user\"\"\"
    progress_data = load_user_progress()
    user_progress = {}
    
    for key, data in progress_data.items():
        if data.get('user_fingerprint') == user_fingerprint:
            module_id = data.get('module_id')
            if module_id is not None:
                user_progress[str(module_id)] = data
    
    return user_progress

def generate_user_fingerprint(request):
    """Generate a unique fingerprint based on IP address, user agent, and other identifying information"""
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    accept_language = request.headers.get('Accept-Language', '')
    accept_encoding = request.headers.get('Accept-Encoding', '')
    
    # Create a fingerprint hash from available data
    fingerprint_data = f"{ip}:{user_agent}:{accept_language}:{accept_encoding}"
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    return fingerprint

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
    return render_template('index.html', config=config, courses=courses)

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
    
    return render_template('course.html', 
                         config=config, 
                         module=module, 
                         module_id=module_id,
                         total_modules=len(courses['modules']),
                         html_content=html_content,
                         quiz=quiz_data)

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
        return jsonify({"error": "Authentication required"}), 401
    
    if request.method == 'POST':
        config = request.json or {}
        save_config(config)
        return jsonify({"success": True})
    else:
        return jsonify(load_config())

@app.route('/admin/modules', methods=['GET', 'POST', 'PUT', 'DELETE'])
def admin_modules():
    """Handle module management"""
    if not session.get('admin_authenticated', False):
        return jsonify({"error": "Authentication required"}), 401
    
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
        if 0 <= module_id < len(courses['modules']):
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
        return jsonify({"error": "Authentication required"}), 401
    
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

@app.route('/generate_certificate')
def generate_certificate():
    """Generate completion certificate"""
    # Verify completion status server-side
    courses = load_courses()
    total_modules = len(courses['modules'])
    
    # Get completion claim from query param
    completed_param = request.args.get('completed', '')
    if not completed_param:
        return "Please complete all modules before generating certificate", 400
    
    try:
        completed_ids = [int(x) for x in completed_param.split(',') if x.strip()]
        # Verify all modules are claimed as completed
        if len(completed_ids) != total_modules or set(completed_ids) != set(range(total_modules)):
            return "All modules must be completed to generate certificate", 400
    except ValueError:
        return "Invalid completion data", 400
    
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
        return jsonify({"error": "Authentication required"}), 401
    
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file selected"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})
    
    if file and file.filename and file.filename.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(file, 'r') as zip_file:
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
                    if member_name in allowed_files:
                        target_dir = allowed_files[member_name]
                        dest_path = os.path.join(target_dir, os.path.basename(member_name))
                    else:
                        # Check allowed directories
                        target_dir = None
                        for prefix, prefix_dir in allowed_dirs.items():
                            if member_name.startswith(prefix):
                                # Extract relative path after prefix
                                rel_path = member_name[len(prefix):]
                                if '/' not in rel_path:  # Only allow files directly in the target dir
                                    dest_path = os.path.join(prefix_dir, secure_filename(rel_path))
                                    target_dir = prefix_dir
                                    break
                        
                        if not target_dir:
                            continue
                    
                    # Final security check - ensure dest is within target
                    dest_path = os.path.abspath(dest_path)
                    if not dest_path.startswith(os.path.abspath(target_dir) + os.sep):
                        continue
                    
                    # Create directory and extract
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with zip_file.open(member) as source, open(dest_path, 'wb') as target:
                        target.write(source.read())
            
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    return jsonify({"success": False, "error": "Invalid file type"})

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('data/modules', exist_ok=True)
    os.makedirs('static/resources', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Initialize data directories
    print("Data directories initialized successfully.")
    
    # Only enable debug in development
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)