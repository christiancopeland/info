class WebSocketManager {
    constructor(url = null) {
        this.url = url || `ws://${window.location.host}/api/v1/websocket/ws`;
        this.maxReconnectAttempts = 5;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 3000; // Start with 3 seconds
        this.ws = null;
        this.currentMessageDiv = null;
        
        console.log('Initializing WebSocket manager');
        this.connect();
    }

    connect() {
        console.log('Connecting to WebSocket...');
        
        // Ensure chat container exists before attempting connection
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) {
            console.error('Chat container not found, delaying connection...');
            setTimeout(() => this.connect(), 1000);
            return;
        }

        try {
            // Create WebSocket connection
            this.ws = new WebSocket(this.url);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected successfully');
                this.reconnectAttempts = 0; // Reset counter on successful connection
                
                // Send initial authentication message
                const authToken = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('auth_token='))
                    ?.split('=')[1];

                if (authToken) {
                    this.sendCommand('authenticate', { token: authToken });
                } else {
                    console.error('No auth token found for WebSocket authentication');
                }
            };

            this.ws.onmessage = (event) => {
                console.log('Message received:', event.data);
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'error') {
                        console.error('WebSocket error:', data.error);
                        this.appendMessage('error', data.error);
                    } else if (data.type === 'chunk') {
                        // Handle streaming chunks
                        this.handleStreamingChunk(data.message);
                    } else if (data.type === 'done') {
                        // Handle completion of streaming
                        this.handleStreamingDone();
                    } else if (data.type === 'command_response') {
                        console.log('Command response received:', data);
                        if (data.command === 'authenticate' && data.status === 'success') {
                            console.log('WebSocket authenticated successfully');
                        }
                    } else {
                        this.appendMessage('assistant', data.message || data.content || 'Empty response');
                    }
                } catch (e) {
                    console.error('Error parsing message:', e);
                    this.appendMessage('error', 'Error processing message from server');
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.appendMessage('error', 'Connection error occurred');
            };

            this.ws.onclose = () => {
                console.log('WebSocket closed');
                this.ws = null;
                this.handleReconnect();
            };

        } catch (error) {
            console.error('Error creating WebSocket:', error);
            this.handleReconnect();
        }
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms...`);
            setTimeout(() => this.connect(), delay);
        } else {
            console.error('Max reconnection attempts reached');
            this.appendMessage('error', 'Unable to establish connection. Please refresh the page.');
        }
    }

    sendChatMessage(message) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected. Current state:', this.ws ? this.ws.readyState : 'null');
            return false;
        }

        try {
            const data = {
                type: 'chat',
                messages: [{
                    role: 'user',
                    content: message
                }]
            };
            console.log('Sending chat message:', data);
            this.ws.send(JSON.stringify(data));
            return true;
        } catch (error) {
            console.error('Error sending chat message:', error);
            return false;
        }
    }

    sendCommand(command, payload) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected for command:', command);
            return false;
        }

        try {
            const data = {
                type: 'command',
                command: command,
                payload: payload
            };
            console.log('Sending command:', data);
            this.ws.send(JSON.stringify(data));
            return true;
        } catch (error) {
            console.error('Error sending command:', error);
            return false;
        }
    }

    appendMessage(role, content) {
        const chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) {
            console.error('Chat messages container not found');
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.textContent = content;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    handleStreamingChunk(message) {
        let messageDiv = this.getCurrentOrCreateMessageDiv();
        messageDiv.textContent += message.content;
        
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    handleStreamingDone() {
        this.currentMessageDiv = null; // Reset for next message
    }

    getCurrentOrCreateMessageDiv() {
        if (!this.currentMessageDiv) {
            const chatMessages = document.getElementById('chat-messages');
            if (!chatMessages) {
                console.error('Chat messages container not found');
                return;
            }

            this.currentMessageDiv = document.createElement('div');
            this.currentMessageDiv.className = 'message assistant';
            chatMessages.appendChild(this.currentMessageDiv);
        }
        return this.currentMessageDiv;
    }
}

// Export the WebSocketManager
window.WebSocketManager = WebSocketManager; 