class DocumentUploader {
    constructor() {
        this.modal = document.getElementById('uploadModal');
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadList = document.getElementById('uploadList');
        this.uploadButton = document.getElementById('uploadDoc');
        this.startUploadButton = document.getElementById('startUpload');
        this.cancelUploadButton = document.getElementById('cancelUpload');
        
        this.files = new Map(); // Store files to upload
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Upload button in document panel
        this.uploadButton.addEventListener('click', () => this.showUploadModal());

        // Modal buttons
        this.startUploadButton.addEventListener('click', () => this.handleUpload());
        this.cancelUploadButton.addEventListener('click', () => this.hideUploadModal());

        // File input change
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));

        // Drag and drop events
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.uploadArea.classList.add('dragover');
        });

        this.uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.uploadArea.classList.remove('dragover');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.uploadArea.classList.remove('dragover');
            this.handleFileSelect(e.dataTransfer.files);
        });

        // Click to select files
        this.uploadArea.addEventListener('click', () => this.fileInput.click());

        // Document tree drag and drop
        const documentTree = document.getElementById('documentTree');
        if (documentTree) {
            documentTree.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                documentTree.classList.add('dragover');
            });

            documentTree.addEventListener('dragleave', (e) => {
                e.preventDefault();
                e.stopPropagation();
                documentTree.classList.remove('dragover');
            });

            documentTree.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                documentTree.classList.remove('dragover');
                this.handleFileSelect(e.dataTransfer.files);
                this.showUploadModal();
            });
        }
    }

    showUploadModal() {
        this.modal.style.display = 'block';
    }

    hideUploadModal() {
        this.modal.style.display = 'none';
        this.files.clear();
        this.renderFileList();
    }

    handleFileSelect(fileList) {
        Array.from(fileList).forEach(file => {
            if (file.type === 'application/pdf') {
                this.files.set(file.name, file);
            } else {
                console.warn(`Skipping file ${file.name}: not a PDF`);
            }
        });
        this.renderFileList();
    }

    renderFileList() {
        this.uploadList.innerHTML = '';
        this.files.forEach((file, name) => {
            const item = document.createElement('div');
            item.className = 'upload-item';
            item.innerHTML = `
                <span class="filename">${name}</span>
                <span class="filesize">${this.formatFileSize(file.size)}</span>
                <button class="remove-file" data-filename="${name}">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            item.querySelector('.remove-file').addEventListener('click', () => {
                this.files.delete(name);
                this.renderFileList();
            });
            
            this.uploadList.appendChild(item);
        });
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async handleUpload() {
        const projectId = window.workspaceManager.currentProject;
        if (!projectId) {
            alert('Please select a project first');
            return;
        }

        for (const [filename, file] of this.files) {
            try {
                console.log(`Starting upload for ${filename} to project ${projectId}`);
                
                const formData = new FormData();
                formData.append('file', file);
                formData.append('project_id', projectId);

                const response = await fetch('/api/v1/documents/upload', {
                    method: 'POST',
                    credentials: 'include',
                    body: formData
                });

                if (!response.ok) {
                    const responseData = await response.json();
                    console.error('Upload failed:', responseData);
                    // Add more specific error handling
                    if (responseData.detail && responseData.detail.includes('UndefinedColumnError')) {
                        throw new Error('Database schema mismatch. May need to update the database schema.');
                    }
                    throw new Error(responseData.detail || `Failed to upload ${filename}`);
                }

                const responseData = await response.json();
                console.log(`Successfully uploaded ${filename}:`, responseData);
                
                // Refresh document list in workspace
                if (window.workspaceManager) {
                    console.log('Refreshing document list...');
                    await window.workspaceManager.loadDocuments();
                }

            } catch (error) {
                console.error(`Error uploading ${filename}:`, error);
                alert(`Failed to upload ${filename}: ${error.message}`);
            }
        }

        this.hideUploadModal();
        this.files.clear();
        this.renderFileList();
    }
}

// Initialize uploader
window.documentUploader = new DocumentUploader();
