class ChatManager {
    constructor() {
        this.chatContainer = document.getElementById('chat-messages');
        this.chatInput = document.getElementById('chat-input');
        this.sendButton = document.getElementById('send-button');
        this.currentConversationId = null;
        this.isProcessing = false;
        
        if (!this.chatContainer || !this.chatInput || !this.sendButton) {
            console.error('Required chat elements not found:', {
                chatContainer: !!this.chatContainer,
                chatInput: !!this.chatInput,
                sendButton: !!this.sendButton
            });
            return;
        }

        this.setupEventListeners();
        console.log('ChatManager initialized');
    }

    setupEventListeners() {
        // Handle Enter key in textarea
        this.chatInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.stopPropagation();
                this.sendChatMessage();
            }
        });

        // Handle send button click
        this.sendButton.addEventListener('click', (event) => {
            event.preventDefault();
            this.sendChatMessage();
        });

        // Listen for conversation selection
        document.addEventListener('conversationSelected', async (event) => {
            console.log('Conversation selected:', event.detail.conversationId);
            this.currentConversationId = event.detail.conversationId;
            await this.loadConversationHistory();
        });
    }

    async loadConversationHistory() {
        if (!this.currentConversationId) return;

        try {
            console.log(`Loading conversation history for: ${this.currentConversationId}`);
            const response = await fetch(`/api/v1/projects/${this.currentConversationId}/messages`);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('API error response:', errorText);
                throw new Error(`Failed to load conversation history: ${response.status}`);
            }
            
            const messages = await response.json();
            console.log('Received messages:', messages);
            
            // Clear existing messages
            this.chatContainer.innerHTML = '';
            
            // Add each message to the chat
            if (Array.isArray(messages)) {
                messages.forEach(msg => {
                    // Check if the message has the expected structure
                    if (msg && typeof msg === 'object' && 'role' in msg && 'content' in msg) {
                        this.appendMessageToUI(msg.role, msg.content);
                    } else {
                        console.warn('Unexpected message format:', msg);
                    }
                });
            } else {
                console.error('Expected array of messages but got:', typeof messages);
            }

            // Scroll to bottom
            this.scrollToBottom();
        } catch (error) {
            console.error('Error loading conversation history:', error);
            this.showError('Failed to load conversation history');
        }
    }

    appendMessageToUI(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = marked.parse(content); // Assuming marked.js is available for markdown
        
        messageDiv.appendChild(contentDiv);
        this.chatContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }

    showError(message) {
        // Add error message to UI
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        this.chatContainer.appendChild(errorDiv);
        setTimeout(() => errorDiv.remove(), 5000);
    }

    setProcessingState(isProcessing) {
        this.isProcessing = isProcessing;
        this.sendButton.disabled = isProcessing;
        this.chatInput.disabled = isProcessing;
        
        // Update UI to show processing state
        if (isProcessing) {
            this.sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        } else {
            this.sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    }

    async sendChatMessage() {
        const message = this.chatInput.value.trim();
        
        if (!message || !this.currentConversationId || this.isProcessing) {
            return;
        }

        try {
            this.setProcessingState(true);
            
            // Immediately append user message to UI
            this.appendMessageToUI('user', message);
            
            // Clear input right after showing the message
            this.chatInput.value = '';

            // Create assistant message container for streaming
            const assistantMessageDiv = document.createElement('div');
            assistantMessageDiv.className = 'message assistant-message';
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            assistantMessageDiv.appendChild(contentDiv);
            this.chatContainer.appendChild(assistantMessageDiv);

            const response = await fetch(`/api/v1/projects/${this.currentConversationId}/messages`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify({ message: message })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to send message');
            }
            
            let assistantResponse = '';
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.type === 'chunk') {
                                assistantResponse += data.content;
                                contentDiv.innerHTML = marked.parse(assistantResponse);
                                this.scrollToBottom();
                            } else if (data.type === 'error') {
                                throw new Error(data.content);
                            } else if (data.type === 'done') {
                                // Final message received, no further action needed
                                break;
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e);
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Error sending message:', error);
            this.showError('Failed to send message');
            // Remove the incomplete assistant message if there was an error
            assistantMessageDiv?.remove();
        } finally {
            this.setProcessingState(false);
        }
    }
}

// Initialize chat when the chatReady event is fired
document.addEventListener('chatReady', () => {
    console.log('Chat ready event received, initializing ChatManager');
    window.chatManager = new ChatManager();
});
