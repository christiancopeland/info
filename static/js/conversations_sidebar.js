class ConversationsSidebar {
    constructor() {
        this.sidebarContent = document.getElementById('sidebar-content');
        this.currentProjectId = null;
        this.conversations = [];
        this.selectedConversationId = null;
        
        this.setupEventListeners();
        this.initializeSidebarUI();
    }

    initializeSidebarUI() {
        if (this.sidebarContent) {
            this.sidebarContent.innerHTML = `
                <div class="conversations-container">
                    <div class="conversations-header">
                        <h2>Conversations</h2>
                    </div>
                    <div class="new-conversation-btn" onclick="conversationsSidebar.createNewConversation()">
                        <i class="fas fa-plus"></i> New Conversation
                    </div>
                    <div class="conversations-list"></div>
                    <div class="conversations-empty-state hidden">
                        <i class="fas fa-comments"></i>
                        <p>No conversations yet</p>
                        <p>Start a new conversation to begin</p>
                    </div>
                </div>
            `;

            // Initially disable the new conversation button
            this.updateNewConversationButton();
        }
    }

    updateNewConversationButton() {
        const newConversationBtn = this.sidebarContent?.querySelector('.new-conversation-btn');
        if (newConversationBtn) {
            if (!this.currentProjectId) {
                newConversationBtn.classList.add('disabled');
                newConversationBtn.title = 'Please select a project first';
            } else {
                newConversationBtn.classList.remove('disabled');
                newConversationBtn.title = 'Create new conversation';
            }
        }
    }

    setupEventListeners() {
        // Listen for project selection
        document.addEventListener('projectSelected', async (event) => {
            console.log('Project selected event received:', event.detail);
            this.currentProjectId = event.detail.projectId;
            this.updateNewConversationButton();
            await this.loadConversations();
        });
    }

    async loadConversations() {
        try {
            const response = await fetch(`/api/v1/projects/${this.currentProjectId}/conversations`);
            if (!response.ok) throw new Error('Failed to load conversations');
            
            this.conversations = await response.json();
            this.renderConversations();
        } catch (error) {
            console.error('Error loading conversations:', error);
        }
    }

    renderConversations() {
        const conversationsList = this.sidebarContent?.querySelector('.conversations-list');
        const emptyState = this.sidebarContent?.querySelector('.conversations-empty-state');
        
        if (!conversationsList || !emptyState) return;

        if (this.conversations.length === 0) {
            conversationsList.innerHTML = '';
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
            conversationsList.innerHTML = this.conversations
                .map(conv => this.renderConversationItem(conv))
                .join('');
        }
    }

    renderConversationItem(conversation) {
        const isSelected = conversation.id === this.selectedConversationId;
        const lastMessage = conversation.last_message?.content || 'No messages yet';
        const truncatedMessage = lastMessage.length > 60 ? 
            lastMessage.substring(0, 57) + '...' : lastMessage;

        return `
            <div class="conversation-item ${isSelected ? 'selected' : ''}" 
                 data-id="${conversation.id}"
                 onclick="conversationsSidebar.selectConversation('${conversation.id}')">
                <div class="conversation-item-content">
                    <div class="conversation-name">
                        <i class="fas fa-comment-alt"></i>
                        ${conversation.name}
                    </div>
                    <div class="conversation-preview">${truncatedMessage}</div>
                    <div class="conversation-time">
                        ${this.formatDate(conversation.updated_at)}
                    </div>
                </div>
            </div>
        `;
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;
        
        // If less than 24 hours, show time
        if (diff < 24 * 60 * 60 * 1000) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        // If this year, show month and day
        if (date.getFullYear() === now.getFullYear()) {
            return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
        // Otherwise show date with year
        return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
    }

    async createNewConversation() {
        if (!this.currentProjectId) {
            console.warn('No project selected');
            return;
        }

        try {
            const name = `New Conversation ${this.conversations.length + 1}`;
            const response = await fetch(`/api/v1/projects/${this.currentProjectId}/conversations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name: name })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to create conversation');
            }
            
            const newConversation = await response.json();
            await this.loadConversations();
            this.selectConversation(newConversation.id);
        } catch (error) {
            console.error('Error creating conversation:', error);
        }
    }

    async selectConversation(conversationId) {
        this.selectedConversationId = conversationId;
        
        // Dispatch event for conversation selection
        const event = new CustomEvent('conversationSelected', {
            detail: { conversationId }
        });
        document.dispatchEvent(event);
        
        // Re-render to update selection state
        this.renderConversations();
    }
}



// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.conversationsSidebar = new ConversationsSidebar();
}); 