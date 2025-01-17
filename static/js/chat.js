class ChatManager {
    constructor() {
        this.chatContainer = document.getElementById('chat-messages');
        this.chatInput = document.getElementById('chat-input');
        this.sendButton = document.getElementById('send-button');
        
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
                console.log('Enter key pressed, attempting to send message');
                this.sendChatMessage();
            }
        });

        // Handle send button click
        this.sendButton.addEventListener('click', (event) => {
            event.preventDefault();
            console.log('Send button clicked, attempting to send message');
            this.sendChatMessage();
        });
    }

    sendChatMessage() {
        const message = this.chatInput.value.trim();
        
        if (!message) {
            console.log('No message to send');
            return;
        }

        console.log('Attempting to send message:', message);

        if (!window.wsManager) {
            console.error('WebSocket manager is not initialized');
            return;
        }

        if (!window.wsManager.ws || window.wsManager.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected');
            return;
        }

        const sent = window.wsManager.sendChatMessage(message);
        if (sent) {
            console.log('Message sent successfully');
            this.chatInput.value = ''; // Clear input after sending
            
            // Add user message to chat container immediately
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'message user';
            userMessageDiv.textContent = message;
            this.chatContainer.appendChild(userMessageDiv);
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
        } else {
            console.error('Failed to send message');
        }
    }
}

// Initialize chat when the chatReady event is fired
document.addEventListener('chatReady', () => {
    console.log('Chat ready event received, initializing ChatManager');
    window.initializeChat(); // This creates the WebSocketManager
    window.chatManager = new ChatManager();
});
