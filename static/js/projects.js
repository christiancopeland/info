class ProjectManager {
    constructor() {
        this.projectsList = document.getElementById('projectsList');
        this.createProjectBtn = document.getElementById('createProject');
        this.projectModal = document.getElementById('projectModal');
        this.projects = new Map();

        // Only set up event listeners initially
        this.setupEventListeners();
        
        // Wait for DOM content to be loaded before checking auth
        document.addEventListener('DOMContentLoaded', () => {
            this.waitForAuthAndLoadProjects();
        });
    }

    async waitForAuthAndLoadProjects() {
        console.log('Waiting for authentication...');
        
        // If already authenticated, load projects
        if (window.authManager && window.authManager.isAuthenticated) {
            console.log('Already authenticated, loading projects...');
            await this.loadProjects();
        } else {
            console.log('Not authenticated, waiting for auth state change...');
            // Wait for auth to be ready
            document.addEventListener('authStateChanged', async () => {
                console.log('Auth state changed, checking authentication...');
                if (window.authManager && window.authManager.isAuthenticated) {
                    console.log('Now authenticated, loading projects...');
                    await this.loadProjects();
                } else {
                    console.log('Still not authenticated after state change');
                }
            });
        }
    }

    setupEventListeners() {
        // Create project button
        this.createProjectBtn.addEventListener('click', () => this.showProjectModal());

        // Modal buttons
        document.getElementById('saveProject').addEventListener('click', () => this.handleCreateProject());
        document.getElementById('cancelProject').addEventListener('click', () => this.hideProjectModal());
    }

    async loadProjects() {
        try {
            console.log('Loading projects...');
            const response = await fetch('/api/v1/projects/', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to load projects');
            }

            const projects = await response.json();
            console.log('Projects loaded:', projects);
            
            this.projects.clear();
            this.projectsList.innerHTML = '';
            
            projects.forEach(project => {
                this.projects.set(project.id, project);
                this.addProjectToList(project);
            });
        } catch (error) {
            console.error('Failed to load projects:', error);
            throw error;
        }
    }

    addProjectToList(project) {
        const projectElement = document.createElement('div');
        projectElement.className = 'project-item';
        projectElement.innerHTML = `
            <div class="project-header">
                <div class="project-info" style="flex: 1;">
                    <h4>${project.name}</h4>
                    <span class="project-date">${new Date(project.created_at).toLocaleDateString()}</span>
                </div>
                <button class="project-settings-btn" title="Project Settings">
                    <i class="fas fa-ellipsis-v"></i>
                </button>
            </div>
            ${project.description ? `<p class="project-description">${project.description}</p>` : ''}
        `;

        // Add click handler to select project (but not when clicking settings)
        const projectInfo = projectElement.querySelector('.project-info');
        projectInfo.addEventListener('click', () => {
            // Instead of directly calling selectProject, dispatch the event with details
            document.dispatchEvent(new CustomEvent('projectSelected', {
                detail: {
                    projectId: project.id,
                    name: project.name
                }
            }));
            this.selectProject(project.id);  // Call selectProject after dispatching event
        });

        // Add settings button handler
        const settingsBtn = projectElement.querySelector('.project-settings-btn');
        settingsBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent project selection when clicking settings
            this.showProjectSettings(project);
        });

        this.projectsList.appendChild(projectElement);
        this.projects.set(project.id, project);
    }

    async handleCreateProject() {
        const nameInput = document.getElementById('projectNameInput');
        const descInput = document.getElementById('projectDescriptionInput');

        const name = nameInput.value.trim();
        const description = descInput.value.trim();

        if (!name) {
            alert('Project name is required');
            return;
        }

        try {
            const params = new URLSearchParams();
            params.append('name', name);
            if (description) {
                params.append('description', description);
            }

            const response = await fetch('/api/v1/projects/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                credentials: 'include',
                body: params
            });

            if (response.ok) {
                const project = await response.json();
                this.addProjectToList(project);
                this.hideProjectModal();
                this.clearModalInputs();

                // Notify WebSocket of new project
                if (window.wsManager) {
                    window.wsManager.sendCommand('project_context', {
                        action: 'create',
                        projectId: project.id,
                        name: project.name
                    });
                }
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to create project');
            }
        } catch (error) {
            console.error('Error creating project:', error);
            alert('Failed to create project');
        }
    }

    async selectProject(projectId) {
        try {
            const response = await fetch(`/api/v1/projects/${projectId}/select`, {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                // Update UI elements
                const projectName = this.projects.get(projectId)?.name || 'Unknown Project';
                document.getElementById('current-project-name').textContent = projectName;
                
                // Update selected project styling
                document.querySelectorAll('.project-item').forEach(item => {
                    item.classList.remove('selected');
                });
                document.querySelector(`[data-project-id="${projectId}"]`)?.classList.add('selected');

                // Initialize workspace
                if (window.workspaceManager) {
                    await window.workspaceManager.initializeWorkspace(projectId);
                }

                // Notify WebSocket of project context change
                if (window.wsManager) {
                    window.wsManager.sendCommand('project_context', {
                        action: 'select',
                        projectId: projectId,
                        name: projectName
                    });
                }
            }
        } catch (error) {
            console.error('Error selecting project:', error);
        }
    }

    showProjectModal() {
        this.projectModal.style.display = 'block';
    }

    hideProjectModal() {
        this.projectModal.style.display = 'none';
        this.clearModalInputs();
    }

    clearModalInputs() {
        document.getElementById('projectNameInput').value = '';
        document.getElementById('projectDescriptionInput').value = '';
    }

    showProjectSettings(project) {
        // Create modal if it doesn't exist
        let settingsModal = document.getElementById('projectSettingsModal');
        if (!settingsModal) {
            settingsModal = document.createElement('div');
            settingsModal.id = 'projectSettingsModal';
            settingsModal.className = 'modal';
            settingsModal.innerHTML = `
                <div class="modal-content">
                    <h3>Project Settings</h3>
                    <form id="projectSettingsForm">
                        <div class="form-group">
                            <label for="editProjectName">Name</label>
                            <input type="text" id="editProjectName" required>
                        </div>
                        <div class="form-group">
                            <label for="editProjectDescription">Description</label>
                            <textarea id="editProjectDescription"></textarea>
                        </div>
                        <div class="button-group">
                            <button type="button" id="updateProjectBtn" class="btn btn-primary">Update</button>
                            <button type="button" id="deleteProjectBtn" class="btn btn-danger">Delete Project</button>
                            <button type="button" id="cancelSettingsBtn" class="btn">Cancel</button>
                        </div>
                    </form>
                </div>
            `;
            document.body.appendChild(settingsModal);

            // Add event listeners for the new modal
            this.setupSettingsModalListeners(settingsModal);
        }

        // Populate form with current project data
        document.getElementById('editProjectName').value = project.name;
        document.getElementById('editProjectDescription').value = project.description || '';

        // Store current project ID
        settingsModal.dataset.projectId = project.id;

        // Show the modal
        settingsModal.style.display = 'block';
    }

    setupSettingsModalListeners(modal) {
        const updateBtn = modal.querySelector('#updateProjectBtn');
        const deleteBtn = modal.querySelector('#deleteProjectBtn');
        const cancelBtn = modal.querySelector('#cancelSettingsBtn');

        updateBtn.addEventListener('click', () => this.handleUpdateProject(modal));
        deleteBtn.addEventListener('click', () => this.handleDeleteProject(modal));
        cancelBtn.addEventListener('click', () => modal.style.display = 'none');
    }

    async handleUpdateProject(modal) {
        const projectId = modal.dataset.projectId;
        const name = document.getElementById('editProjectName').value.trim();
        const description = document.getElementById('editProjectDescription').value.trim();

        if (!name) {
            alert('Project name is required');
            return;
        }

        try {
            const response = await fetch(`/api/v1/projects/${projectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ name, description })
            });

            if (response.ok) {
                await this.loadProjects(); // Reload projects
                modal.style.display = 'none';
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to update project');
            }
        } catch (error) {
            console.error('Error updating project:', error);
            alert('Failed to update project');
        }
    }

    async handleDeleteProject(modal) {
        const projectId = modal.dataset.projectId;
        
        if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/projects/${projectId}`, {
                method: 'DELETE',
                credentials: 'include'
            });

            if (response.ok) {
                await this.loadProjects(); // Reload projects
                modal.style.display = 'none';
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to delete project');
            }
        } catch (error) {
            console.error('Error deleting project:', error);
            alert('Failed to delete project');
        }
    }
}

// Wait for AuthManager to be available before initializing ProjectManager
function initializeProjectManager() {
    if (window.authManager) {
        window.projectManager = new ProjectManager();
    } else {
        setTimeout(initializeProjectManager, 100);
    }
}

// Start initialization process
initializeProjectManager();
