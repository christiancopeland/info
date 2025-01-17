class ProjectWorkspace {
    constructor() {
        this.currentProject = null;
        this.documentTree = document.getElementById('documentTree');
        this.chatMessages = document.getElementById('chat-messages');
        this.newsFeed = document.getElementById('newsFeed');
        this.entityList = document.getElementById('entityList');
        
        this.setupEventListeners();
        this.initializeDocumentControls();
    }

    setupEventListeners() {
        // Panel toggle buttons
        document.getElementById('toggleDocPanel').addEventListener('click', () => 
            this.togglePanel('documentPanel'));
        document.getElementById('toggleNewsPanel').addEventListener('click', () => 
            this.togglePanel('contextPanel'));

        // Tab buttons
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => this.switchTab(e.target));
        });
    }

    togglePanel(panelId) {
        const panel = document.getElementById(panelId);
        if (panel) {
            panel.classList.toggle('collapsed');
            console.log(`Panel ${panelId} toggled:`, panel.classList.contains('collapsed'));
        }
    }

    switchTab(button) {
        // Remove active class from all tabs
        document.querySelectorAll('.tab-button').forEach(tab => 
            tab.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => 
            content.classList.remove('active'));

        // Add active class to clicked tab and its content
        button.classList.add('active');
        const tabId = button.dataset.tab;
        document.getElementById(tabId).classList.add('active');
    }

    async initializeWorkspace(projectId) {
        try {
            this.currentProject = projectId;
            console.log('Initializing workspace for project:', projectId);
            
            // Load documents first
            await this.loadDocuments();
            
            // Only try to load news if we have the newsFeed element
            if (this.newsFeed) {
                await this.loadNews().catch(err => {
                    console.warn('News loading failed:', err);
                });
            }
            
        } catch (error) {
            console.error('Error initializing workspace:', error);
        }
    }

    async loadDocuments() {
        try {
            if (!this.currentProject) {
                this.renderDocumentTree([]);
                return;
            }

            const response = await fetch(`/api/v1/projects/${this.currentProject}/documents`, {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to load documents');
            }

            const documents = await response.json();
            this.renderDocumentTree(documents);
            
        } catch (error) {
            console.error('Error loading documents:', error);
            this.renderDocumentTree([]); // Render empty state on error
        }
    }

    async loadNews() {
        // Placeholder for future news loading functionality
        console.log('News loading not yet implemented');
    }

    renderDocumentTree(documents) {
        if (!this.documentTree) return;
        
        this.documentTree.innerHTML = '';
        
        if (!documents.length) {
            this.documentTree.innerHTML = '<div class="empty-state">No documents yet</div>';
            return;
        }

        documents.forEach(doc => {
            const item = document.createElement('div');
            item.className = 'document-tree-item';
            item.dataset.docId = doc.document_id;
            
            item.innerHTML = `
                <div class="doc-info">
                    <div class="doc-name">${doc.filename}</div>
                    <div class="status">${doc.processing_status}</div>
                    ${doc.processing_status === 'processing' ? `
                        <div class="progress">
                            <div class="progress-bar" style="width: ${doc.progress || 0}%"></div>
                        </div>
                    ` : ''}
                </div>
            `;
            
            item.addEventListener('click', () => this.selectDocument(doc.document_id));
            this.documentTree.appendChild(item);
        });
    }

    selectDocument(docId) {
        console.log('Selected document:', docId);
        // Placeholder for document selection functionality
    }

    updateDocumentProgress(docId, progress, status) {
        const item = this.documentTree.querySelector(`[data-doc-id="${docId}"]`);
        if (!item) return;
        
        const statusEl = item.querySelector('.status');
        const progressBar = item.querySelector('.progress-bar');
        
        if (statusEl) statusEl.textContent = status;
        if (progressBar) progressBar.style.width = `${progress}%`;
    }

    initializeDocumentControls() {
        // Initialize upload button
        this.uploadButton = document.getElementById('uploadDoc');
        if (this.uploadButton) {
            this.uploadButton.addEventListener('click', () => {
                if (window.documentUploader) {
                    window.documentUploader.showUploadModal();
                }
            });
        }
    }

    // Additional methods for handling documents, news, and entities
}

// Initialize workspace manager
window.workspaceManager = new ProjectWorkspace();

