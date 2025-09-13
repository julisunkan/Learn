// Admin Panel JavaScript

let currentModules = [];
let currentEditingModule = -1;
let autoSaveInterval;

// Admin Login Functions
function initializeAdminLogin() {
    const loginForm = document.getElementById('adminLoginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            verifyPasscode();
        });
    }
}

function verifyPasscode() {
    const passcode = document.getElementById('passcode').value;
    
    fetch('/admin/verify_passcode', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ passcode: passcode })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/admin/dashboard';
        } else {
            showAlert('Invalid passcode. Please try again.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error verifying passcode.', 'danger');
    });
}

// Admin Dashboard Functions
function initializeAdminDashboard() {
    // Initialize drag and drop for modules
    const modulesList = document.getElementById('modulesList');
    if (modulesList) {
        new Sortable(modulesList, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: function(evt) {
                updateModuleOrder();
            }
        });
    }
    
    // Initialize config form
    const configForm = document.getElementById('configForm');
    if (configForm) {
        configForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveConfiguration();
        });
        
        // Load current values
        loadConfiguration();
    }
    
    // Initialize import form
    const importForm = document.getElementById('importForm');
    if (importForm) {
        importForm.addEventListener('submit', function(e) {
            e.preventDefault();
            importCourse();
        });
    }
}

// Module Management Functions
function loadModules() {
    fetch('/admin/modules')
        .then(response => response.json())
        .then(data => {
            currentModules = data.modules || [];
            renderModulesList();
        })
        .catch(error => {
            console.error('Error loading modules:', error);
            showAlert('Error loading modules.', 'danger');
        });
}

function renderModulesList() {
    const modulesList = document.getElementById('modulesList');
    if (!modulesList) return;
    
    if (currentModules.length === 0) {
        modulesList.innerHTML = '<p class="text-muted text-center py-4">No modules created yet. Click "Add Module" to get started.</p>';
        return;
    }
    
    modulesList.innerHTML = currentModules.map((module, index) => `
        <div class="card mb-3 module-item" data-module-id="${index}">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="card-title mb-1">
                            <i class="bi bi-grip-vertical text-muted me-2"></i>
                            ${module.title}
                        </h6>
                        <p class="card-text text-muted small mb-2">${module.description || 'No description'}</p>
                        <div class="small text-muted">
                            ${module.duration ? `<i class="bi bi-clock"></i> ${module.duration} min` : ''}
                            ${module.video_url ? '<i class="bi bi-play-circle ms-2"></i> Video' : ''}
                            ${module.quiz && module.quiz.questions ? `<i class="bi bi-question-circle ms-2"></i> ${module.quiz.questions.length} questions` : ''}
                        </div>
                    </div>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-primary" onclick="editModule(${index})">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="previewModule(${index})">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteModule(${index})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

function showAddModuleModal() {
    currentEditingModule = -1;
    document.getElementById('moduleModalTitle').textContent = 'Add New Module';
    clearModuleForm();
    
    const modal = new bootstrap.Modal(document.getElementById('moduleModal'));
    modal.show();
}

function editModule(moduleId) {
    if (moduleId < 0 || moduleId >= currentModules.length) return;
    
    currentEditingModule = moduleId;
    const module = currentModules[moduleId];
    
    document.getElementById('moduleModalTitle').textContent = 'Edit Module';
    populateModuleForm(module);
    
    const modal = new bootstrap.Modal(document.getElementById('moduleModal'));
    modal.show();
}

function clearModuleForm() {
    document.getElementById('moduleTitle').value = '';
    document.getElementById('moduleDescription').value = '';
    document.getElementById('moduleVideoUrl').value = '';
    document.getElementById('moduleDuration').value = '';
    document.getElementById('moduleContent').value = '';
    document.getElementById('resourcesList').innerHTML = '';
    document.getElementById('quizQuestions').innerHTML = '';
}

function populateModuleForm(module) {
    document.getElementById('moduleTitle').value = module.title || '';
    document.getElementById('moduleDescription').value = module.description || '';
    document.getElementById('moduleVideoUrl').value = module.video_url || '';
    document.getElementById('moduleDuration').value = module.duration || '';
    
    // Load content from file if exists
    if (module.content_file) {
        fetch(`/data/modules/${module.content_file}`)
            .then(response => response.text())
            .then(content => {
                document.getElementById('moduleContent').value = content;
            })
            .catch(error => console.error('Error loading content:', error));
    } else {
        document.getElementById('moduleContent').value = '';
    }
    
    // Populate resources
    renderResourcesList(module.resources || []);
    
    // Populate quiz questions
    renderQuizQuestions(module.quiz?.questions || []);
}

function renderResourcesList(resources) {
    const resourcesList = document.getElementById('resourcesList');
    resourcesList.innerHTML = resources.map((resource, index) => `
        <div class="input-group mb-2">
            <input type="text" class="form-control form-control-sm" placeholder="Resource name" value="${resource.name}" onchange="updateResource(${index}, 'name', this.value)">
            <input type="url" class="form-control form-control-sm" placeholder="Resource URL" value="${resource.url}" onchange="updateResource(${index}, 'url', this.value)">
            <button class="btn btn-sm btn-outline-danger" onclick="removeResource(${index})">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `).join('');
}

function renderQuizQuestions(questions) {
    const quizQuestions = document.getElementById('quizQuestions');
    quizQuestions.innerHTML = questions.map((question, qIndex) => `
        <div class="card mb-3 quiz-question" data-question-id="${qIndex}">
            <div class="card-header">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">Question ${qIndex + 1}</h6>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeQuizQuestion(${qIndex})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="mb-3">
                    <input type="text" class="form-control" placeholder="Enter question" value="${question.question}" onchange="updateQuizQuestion(${qIndex}, 'question', this.value)">
                </div>
                <div class="mb-3">
                    <label class="form-label small">Options:</label>
                    ${question.options.map((option, oIndex) => `
                        <div class="input-group mb-1">
                            <div class="input-group-text">
                                <input type="radio" name="correct_${qIndex}" value="${oIndex}" ${question.correct_answer === oIndex ? 'checked' : ''} onchange="updateQuizQuestion(${qIndex}, 'correct_answer', ${oIndex})">
                            </div>
                            <input type="text" class="form-control" placeholder="Option ${oIndex + 1}" value="${option}" onchange="updateQuizOption(${qIndex}, ${oIndex}, this.value)">
                            <button class="btn btn-outline-danger btn-sm" onclick="removeQuizOption(${qIndex}, ${oIndex})">
                                <i class="bi bi-dash"></i>
                            </button>
                        </div>
                    `).join('')}
                    <button class="btn btn-sm btn-outline-primary mt-1" onclick="addQuizOption(${qIndex})">
                        <i class="bi bi-plus"></i> Add Option
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

function addResource() {
    // Get current resources
    const resourceInputs = document.querySelectorAll('#resourcesList .input-group');
    const resources = Array.from(resourceInputs).map(group => ({
        name: group.querySelector('input[type="text"]').value,
        url: group.querySelector('input[type="url"]').value
    }));
    
    resources.push({ name: '', url: '' });
    renderResourcesList(resources);
}

function removeResource(index) {
    const resourceInputs = document.querySelectorAll('#resourcesList .input-group');
    const resources = Array.from(resourceInputs).map(group => ({
        name: group.querySelector('input[type="text"]').value,
        url: group.querySelector('input[type="url"]').value
    }));
    
    resources.splice(index, 1);
    renderResourcesList(resources);
}

function addQuizQuestion() {
    const questionsContainer = document.getElementById('quizQuestions');
    const currentQuestions = getCurrentQuizQuestions();
    
    currentQuestions.push({
        question: '',
        options: ['', ''],
        correct_answer: 0
    });
    
    renderQuizQuestions(currentQuestions);
}

function removeQuizQuestion(qIndex) {
    const currentQuestions = getCurrentQuizQuestions();
    currentQuestions.splice(qIndex, 1);
    renderQuizQuestions(currentQuestions);
}

function addQuizOption(qIndex) {
    const currentQuestions = getCurrentQuizQuestions();
    currentQuestions[qIndex].options.push('');
    renderQuizQuestions(currentQuestions);
}

function removeQuizOption(qIndex, oIndex) {
    const currentQuestions = getCurrentQuizQuestions();
    if (currentQuestions[qIndex].options.length > 2) { // Keep at least 2 options
        currentQuestions[qIndex].options.splice(oIndex, 1);
        // Adjust correct answer if needed
        if (currentQuestions[qIndex].correct_answer >= oIndex) {
            currentQuestions[qIndex].correct_answer = Math.max(0, currentQuestions[qIndex].correct_answer - 1);
        }
        renderQuizQuestions(currentQuestions);
    }
}

function getCurrentQuizQuestions() {
    const questionCards = document.querySelectorAll('.quiz-question');
    return Array.from(questionCards).map(card => {
        const qIndex = card.dataset.questionId;
        const question = card.querySelector('input[type="text"]').value;
        const options = Array.from(card.querySelectorAll('.input-group input[type="text"]')).map(input => input.value);
        const correctRadio = card.querySelector('input[type="radio"]:checked');
        const correct_answer = correctRadio ? parseInt(correctRadio.value) : 0;
        
        return { question, options, correct_answer };
    });
}

function updateQuizQuestion(qIndex, field, value) {
    // This is handled by the onchange events in the rendered HTML
}

function updateQuizOption(qIndex, oIndex, value) {
    // This is handled by the onchange events in the rendered HTML
}

function updateResource(index, field, value) {
    // This is handled by the onchange events in the rendered HTML
}

function saveModule() {
    const moduleData = {
        title: document.getElementById('moduleTitle').value,
        description: document.getElementById('moduleDescription').value,
        video_url: document.getElementById('moduleVideoUrl').value,
        duration: parseInt(document.getElementById('moduleDuration').value) || null,
        content: document.getElementById('moduleContent').value
    };
    
    // Validate required fields
    if (!moduleData.title.trim()) {
        showAlert('Module title is required.', 'warning');
        return;
    }
    
    // Get resources
    const resourceInputs = document.querySelectorAll('#resourcesList .input-group');
    const resources = Array.from(resourceInputs).map(group => ({
        name: group.querySelector('input[type="text"]').value,
        url: group.querySelector('input[type="url"]').value
    })).filter(resource => resource.name.trim() && resource.url.trim());
    
    if (resources.length > 0) {
        moduleData.resources = resources;
    }
    
    // Get quiz questions
    const quizQuestions = getCurrentQuizQuestions().filter(q => q.question.trim());
    if (quizQuestions.length > 0) {
        moduleData.quiz = { questions: quizQuestions };
    }
    
    // Save module
    if (currentEditingModule === -1) {
        // Add new module
        fetch('/admin/modules', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(moduleData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('Module added successfully!', 'success');
                loadModules();
                bootstrap.Modal.getInstance(document.getElementById('moduleModal')).hide();
            } else {
                showAlert('Error adding module.', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('Error adding module.', 'danger');
        });
    } else {
        // Update existing module
        currentModules[currentEditingModule] = { ...currentModules[currentEditingModule], ...moduleData };
        
        fetch('/admin/modules', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ modules: currentModules })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('Module updated successfully!', 'success');
                loadModules();
                bootstrap.Modal.getInstance(document.getElementById('moduleModal')).hide();
            } else {
                showAlert('Error updating module.', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('Error updating module.', 'danger');
        });
    }
}

function deleteModule(moduleId) {
    if (!confirm('Are you sure you want to delete this module? This action cannot be undone.')) {
        return;
    }
    
    fetch('/admin/modules', {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ module_id: moduleId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Module deleted successfully!', 'success');
            loadModules();
        } else {
            showAlert('Error deleting module.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error deleting module.', 'danger');
    });
}

function previewModule(moduleId = -1) {
    const module = moduleId === -1 ? getModuleFromForm() : currentModules[moduleId];
    
    // Open preview in new window
    const previewWindow = window.open('', '_blank', 'width=800,height=600');
    previewWindow.document.write(`
        <html>
            <head>
                <title>Module Preview: ${module.title}</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body class="p-4">
                <h1>${module.title}</h1>
                <p class="text-muted">${module.description || 'No description'}</p>
                ${module.video_url ? `<video src="${module.video_url}" controls class="w-100 mb-3"></video>` : ''}
                <div class="content">${module.content || 'No content'}</div>
                ${module.quiz && module.quiz.questions ? `
                    <h3>Quiz Questions</h3>
                    ${module.quiz.questions.map((q, i) => `
                        <div class="mb-3">
                            <h6>${i + 1}. ${q.question}</h6>
                            <ul>
                                ${q.options.map((opt, oi) => `
                                    <li ${oi === q.correct_answer ? 'style="color: green; font-weight: bold;"' : ''}>${opt}</li>
                                `).join('')}
                            </ul>
                        </div>
                    `).join('')}
                ` : ''}
            </body>
        </html>
    `);
}

function getModuleFromForm() {
    return {
        title: document.getElementById('moduleTitle').value,
        description: document.getElementById('moduleDescription').value,
        video_url: document.getElementById('moduleVideoUrl').value,
        duration: document.getElementById('moduleDuration').value,
        content: document.getElementById('moduleContent').value,
        quiz: { questions: getCurrentQuizQuestions() }
    };
}

function updateModuleOrder() {
    // Get new order from DOM
    const moduleItems = document.querySelectorAll('.module-item');
    const newOrder = Array.from(moduleItems).map(item => {
        const moduleId = parseInt(item.dataset.moduleId);
        return currentModules[moduleId];
    });
    
    // Update server
    fetch('/admin/modules', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ modules: newOrder })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentModules = newOrder;
            showAlert('Module order updated!', 'success');
        } else {
            showAlert('Error updating module order.', 'danger');
            loadModules(); // Reload to reset order
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error updating module order.', 'danger');
        loadModules(); // Reload to reset order
    });
}

// Configuration Functions
function loadConfiguration() {
    fetch('/admin/config')
        .then(response => response.json())
        .then(config => {
            document.getElementById('siteTitle').value = config.site_title || '';
            document.getElementById('siteDescription').value = config.site_description || '';
            document.getElementById('primaryColor').value = config.primary_color || '#007bff';
            document.getElementById('secondaryColor').value = config.secondary_color || '#6c757d';
            document.getElementById('textColor').value = config.text_color || '#333333';
            document.getElementById('fontSize').value = config.font_size || '16px';
            document.getElementById('fontFamily').value = config.font_family || 'Arial, sans-serif';
            document.getElementById('enablePasscode').checked = config.enable_passcode || false;
            document.getElementById('adminPasscode').value = config.admin_passcode || '';
        })
        .catch(error => {
            console.error('Error loading configuration:', error);
        });
}

function saveConfiguration() {
    const config = {
        site_title: document.getElementById('siteTitle').value,
        site_description: document.getElementById('siteDescription').value,
        primary_color: document.getElementById('primaryColor').value,
        secondary_color: document.getElementById('secondaryColor').value,
        text_color: document.getElementById('textColor').value,
        font_size: document.getElementById('fontSize').value,
        font_family: document.getElementById('fontFamily').value,
        enable_passcode: document.getElementById('enablePasscode').checked,
        admin_passcode: document.getElementById('adminPasscode').value
    };
    
    fetch('/admin/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Configuration saved successfully! Refresh the page to see changes.', 'success');
        } else {
            showAlert('Error saving configuration.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error saving configuration.', 'danger');
    });
}

function initializeConfigPreview() {
    // Add event listeners to form fields for live preview
    const fields = ['siteTitle', 'siteDescription', 'primaryColor', 'secondaryColor', 'textColor', 'fontSize', 'fontFamily'];
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', updateConfigPreview);
        }
    });
}

function updateConfigPreview() {
    const preview = document.getElementById('configPreview');
    const title = document.getElementById('siteTitle').value;
    const description = document.getElementById('siteDescription').value;
    const primaryColor = document.getElementById('primaryColor').value;
    const textColor = document.getElementById('textColor').value;
    const fontSize = document.getElementById('fontSize').value;
    const fontFamily = document.getElementById('fontFamily').value;
    
    // Update preview text
    document.getElementById('previewTitle').textContent = title || 'Tutorial Platform';
    document.getElementById('previewDescription').textContent = description || 'Learn at your own pace';
    
    // Update preview styles
    const previewContainer = preview.querySelector('.preview-container');
    if (previewContainer) {
        previewContainer.style.fontFamily = fontFamily;
        previewContainer.style.fontSize = fontSize;
        previewContainer.style.color = textColor;
    }
    
    const previewNavbar = preview.querySelector('.preview-navbar');
    if (previewNavbar) {
        previewNavbar.style.backgroundColor = primaryColor;
    }
    
    const previewButton = preview.querySelector('button');
    if (previewButton) {
        previewButton.style.backgroundColor = primaryColor;
        previewButton.style.borderColor = primaryColor;
    }
}

// Import/Export Functions
function importCourse() {
    const fileInput = document.getElementById('importFile');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('Please select a ZIP file to import.', 'warning');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/admin/import_course', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Course imported successfully! Please refresh the page.', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showAlert(`Import failed: ${data.error}`, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error importing course.', 'danger');
    });
}

// Feedback Functions
function loadFeedback() {
    // Load feedback from server (if feedback.json exists)
    fetch('/data/feedback.json')
        .then(response => {
            if (response.ok) {
                return response.json();
            }
            return [];
        })
        .then(feedback => {
            renderFeedback(feedback);
        })
        .catch(error => {
            document.getElementById('feedbackList').innerHTML = '<p class="text-muted">No feedback available yet.</p>';
        });
}

function renderFeedback(feedbackList) {
    const feedbackContainer = document.getElementById('feedbackList');
    
    if (!feedbackList || feedbackList.length === 0) {
        feedbackContainer.innerHTML = '<p class="text-muted">No feedback submitted yet.</p>';
        return;
    }
    
    feedbackContainer.innerHTML = feedbackList.map(feedback => `
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <h6>Module ${feedback.module_id + 1}</h6>
                        <div class="mb-2">
                            ${Array(5).fill().map((_, i) => 
                                `<i class="bi bi-star${i < feedback.rating ? '-fill text-warning' : ' text-muted'}"></i>`
                            ).join('')}
                            <span class="ms-2">${feedback.rating}/5</span>
                        </div>
                        ${feedback.comment ? `<p class="mb-0">"${feedback.comment}"</p>` : '<p class="text-muted mb-0">No comment provided</p>'}
                    </div>
                    <small class="text-muted">${new Date(feedback.timestamp).toLocaleDateString()}</small>
                </div>
            </div>
        </div>
    `).join('');
}

// Auto-save Functions
function initializeAutoSave() {
    // Save form data to localStorage periodically
    autoSaveInterval = setInterval(autoSave, 30000); // Save every 30 seconds
    
    // Load saved data on page load
    loadAutoSavedData();
}

function autoSave() {
    const currentTab = document.querySelector('.nav-link.active')?.getAttribute('data-bs-target');
    
    if (currentTab === '#modules' && document.getElementById('moduleModal')?.classList.contains('show')) {
        // Save module form data
        const moduleData = {
            title: document.getElementById('moduleTitle')?.value || '',
            description: document.getElementById('moduleDescription')?.value || '',
            video_url: document.getElementById('moduleVideoUrl')?.value || '',
            duration: document.getElementById('moduleDuration')?.value || '',
            content: document.getElementById('moduleContent')?.value || ''
        };
        localStorage.setItem('admin_autosave_module', JSON.stringify(moduleData));
    } else if (currentTab === '#config') {
        // Save config form data
        const configData = {
            site_title: document.getElementById('siteTitle')?.value || '',
            site_description: document.getElementById('siteDescription')?.value || '',
            primary_color: document.getElementById('primaryColor')?.value || '',
            secondary_color: document.getElementById('secondaryColor')?.value || '',
            text_color: document.getElementById('textColor')?.value || '',
            font_size: document.getElementById('fontSize')?.value || '',
            font_family: document.getElementById('fontFamily')?.value || '',
            enable_passcode: document.getElementById('enablePasscode')?.checked || false,
            admin_passcode: document.getElementById('adminPasscode')?.value || ''
        };
        localStorage.setItem('admin_autosave_config', JSON.stringify(configData));
    }
    
    showAlert('Auto-saved draft', 'info');
    setTimeout(() => {
        document.querySelector('.alert')?.remove();
    }, 2000);
}

function loadAutoSavedData() {
    // Load module form data
    const savedModuleData = localStorage.getItem('admin_autosave_module');
    if (savedModuleData) {
        const moduleData = JSON.parse(savedModuleData);
        // This will be loaded when the modal is shown
    }
    
    // Load config form data
    const savedConfigData = localStorage.getItem('admin_autosave_config');
    if (savedConfigData) {
        const configData = JSON.parse(savedConfigData);
        // This will override the server data if available
        Object.keys(configData).forEach(key => {
            const element = document.getElementById(key.replace('_', ''));
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = configData[key];
                } else {
                    element.value = configData[key];
                }
            }
        });
    }
}

// Utility function
function showAlert(message, type = 'info') {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show position-fixed" 
             style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', alertHtml);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        const alert = document.querySelector('.alert');
        if (alert) {
            alert.remove();
        }
    }, 5000);
}