class DocumentDashboard {
    constructor() {
        console.log('Initializing DocumentDashboard');
        this.container = document.getElementById('documents-container');
        this.template = document.getElementById('document-card-template');
        this.documents = new Map();
    }

    addDocument(documentData) {
        console.log('Adding document with data:', documentData);
        
        // Ensure we have valid metadata with fallbacks
        const metadata = {
            title: this.getMetadataValue(documentData, 'title', 'Untitled Document'),
            author: this.getMetadataValue(documentData, 'author', 'Unknown Author'),
            num_pages: this.getMetadataValue(documentData, 'num_pages', '?'),
            creation_date: this.getMetadataValue(documentData, 'creation_date', new Date().toLocaleDateString())
        };

        // Create document card with sanitized data
        const card = this.createDocumentCard({
            ...documentData,
            metadata: metadata
        });

        this.documents.set(documentData.doc_id, card);
        this.container.prepend(card);
        console.log('Document card added successfully');
    }

    // Helper method to safely get metadata values
    getMetadataValue(documentData, key, defaultValue) {
        try {
            return documentData.metadata?.[key] || 
                   documentData.processing_result?.metadata?.[key] || 
                   (key === 'title' ? documentData.filename : defaultValue);
        } catch (error) {
            console.warn(`Error accessing metadata ${key}:`, error);
            return defaultValue;
        }
    }

    createDocumentCard(documentData) {
        console.log('Creating document card for:', documentData);
        const template = this.template.content.cloneNode(true);
        
        // Set title with overflow handling
        const titleElement = template.querySelector('.doc-title');
        titleElement.textContent = this.getMetadataValue(documentData, 'title', 'Untitled Document');
        titleElement.style.overflow = 'hidden';
        titleElement.style.textOverflow = 'ellipsis';
        titleElement.style.whiteSpace = 'nowrap';
        titleElement.style.width = '100%';
        titleElement.style.display = 'block';
        
        // Set creation date
        template.querySelector('.date').textContent += 
            this.getMetadataValue(documentData, 'creation_date', new Date().toLocaleDateString());

        const card = template.querySelector('.document-card');
        card.id = `doc-${documentData.doc_id}`;
        
        // Remove all elements except title and date
        const elementsToRemove = [
            '.author',
            '.pages',
            '.chunks-list',
            '.progress-container',
            '.status-text'
        ];
        
        elementsToRemove.forEach(selector => {
            const element = card.querySelector(selector);
            if (element) {
                element.remove();
            }
        });
        
        return card;
    }

    updateDocument(docId, updateData) {
        console.log('Updating document:', docId, updateData);
        const card = this.documents.get(docId);
        if (!card) {
            console.warn('Card not found for document:', docId);
            return;
        }

        try {
            if (updateData.total_chunks) {
                const progressBar = card.querySelector('.progress-bar');
                const progress = (updateData.processed_chunks / updateData.total_chunks) * 100;
                progressBar.style.width = `${progress}%`;
            }
        } catch (error) {
            console.error('Error updating document card:', error);
        }
    }

    documentComplete(docId, success, message) {
        console.log('Document processing complete:', docId, success, message);
        const card = this.documents.get(docId);
        if (!card) return;

        // Update status text and hide processing elements
        const statusText = card.querySelector('.status-text');
        if (statusText) {
            statusText.remove(); // Remove the status text completely when done
        }

        // Hide or remove progress bar container
        const progressContainer = card.querySelector('.progress-container');
        if (progressContainer) {
            progressContainer.remove();
        }
    }
}

// Initialize dashboard when the document is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing dashboard...');
    window.dashboard = new DocumentDashboard();
}); 