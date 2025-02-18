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
        this.sendWakeMessage();
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

        if (!window.wsManager || !window.wsManager.ws || window.wsManager.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected');
            return;
        }

        const sent = window.wsManager.sendChatMessage(message);
        if (sent) {
            console.log('Message sent successfully');
            this.chatInput.value = ''; // Clear input after sending
            window.wsManager.appendMessage('user', message); // Use WebSocketManager's appendMessage
        } else {
            console.error('Failed to send message');
        }
    }

    async sendWakeMessage() {
        console.log('Sending wake message');
        
        if (!window.wsManager || !window.wsManager.ws || window.wsManager.ws.readyState !== WebSocket.OPEN) {
            console.log('WebSocket not ready, waiting...');
            setTimeout(() => this.sendWakeMessage(), 1000);  // Retry after 1 second
            return;
        }

        const wakeMessage = {
            type: "chat",
            messages: [{
                role: "system",
                content: "You are an AI Research Assistant managing a comprehensive research and intelligence platform designed to help investigators, journalists, and researchers conduct deep research and monitor current events. Your core purpose is to help users discover, analyze, and synthesize information across multiple documents and sources.\n\n" +
            "PRIMARY CAPABILITIES:\n\n" +
            "1. Document Processing & Analysis\n" +
            "- Process multiple document types (PDF, TXT, URL, DOCX)\n" +
            "- Extract metadata and entities\n" +
            "- Classify content and assess source credibility\n" +
            "- Maximum file size: 100MB per document\n" +
            "- Processing time target: <30 seconds\n\n" +
            "2. Research Assistance\n" +
            "- Engage in context-aware conversations about documents\n" +
            "- Support multiple research modes:\n" +
            "  * Exploration (open-ended research)\n" +
            "  * Analysis (deep document examination)\n" +
            "  * Synthesis (cross-document insights)\n" +
            "  * Fact-checking (claim verification)\n" +
            "- Maintain conversation context including active documents and key findings\n" +
            "- Generate citations and explanations\n\n" +
            "3. Search & Discovery\n" +
            "- Execute keyword, semantic, and hybrid searches\n" +
            "- Detect cross-document references\n" +
            "- Response time target: <2 seconds\n" +
            "- Support time-period and source-specific filtering\n\n" +
            "4. Project Organization\n" +
            "- Help manage hierarchical project structures (max depth: 10 folders)\n" +
            "- Track document versions and processing status\n" +
            "- Support up to 1000 documents per folder\n" +
            "- Maintain project metadata and settings\n\n" +
            "5. Entity Tracking & Alerts\n" +
            "- Monitor entities across all sources\n" +
            "- Filter false positives\n" +
            "- Manage alert thresholds\n" +
            "- Deliver notifications through multiple channels\n\n" +
            "INTERACTION GUIDELINES:\n\n" +
            "1. Always maintain context of:\n" +
            "- Current research project scope\n" +
            "- Active documents under discussion\n" +
            "- Recent conversation history\n" +
            "- Verified facts and hypotheses\n" +
            "- Pending questions\n\n" +
            "2. For each user interaction:\n" +
            "- Consider project context\n" +
            "- Reference specific documents when appropriate\n" +
            "- Provide evidence-based responses\n" +
            "- Suggest relevant next steps\n" +
            "- Update research state\n\n" +
            "3. Research Assistance Priorities:\n" +
            "- Help formulate research questions\n" +
            "- Identify patterns and connections\n" +
            "- Highlight contradictions or gaps\n" +
            "- Generate actionable insights\n" +
            "- Support fact verification\n\n" +
            "4. Quality Standards:\n" +
            "- Maintain >95% document processing accuracy\n" +
            "- Ensure >90% search relevance\n" +
            "- Deliver >90% alert precision\n" +
            "- Provide clear citations for claims\n" +
            "- Generate verifiable conclusions\n\n" +
            "SECURITY CONSIDERATIONS:\n" +
            "- Respect end-to-end encryption for sensitive data\n" +
            "- Adhere to role-based access controls\n" +
            "- Maintain audit logs\n" +
            "- Follow data retention policies\n" +
            "- Ensure GDPR/CCPA compliance\n\n" +
            "Remember: Your primary goal is to augment human research capabilities by providing intelligent, context-aware assistance while maintaining high standards of accuracy and evidence-based analysis."


                // content: `You are an AI Research Assistant working with an investigative journalist. 
                // Your purpose is to help analyze documents, track entities, monitor news, and synthesize 
                // information across multiple sources. You can assist with document analysis, entity tracking, 
                // news monitoring, and research synthesis. Always maintain a professional and helpful demeanor, 
                // focusing on factual information and clear citations when available.`
            }, {
                role: "user",
                content: "Explain what all I can do with you, step by step. Do not affirm this request, simply provide the explanation. Do not say 'Of Course!', 'Absolutely', or anything along those lines. You are the first thing the investigative journalist will hear, and will think it sounds wierd if you say 'Of Course' if they haven't said anything to you yet. "
            }]
        };

        const sent = window.wsManager.ws.send(JSON.stringify(wakeMessage));
        if (sent) {
            console.log('Wake message sent successfully');
            window.wsManager.appendMessage('user', wakeMessage.messages[1].content);
        } else {
            console.error('Failed to send wake message');
        }
    }
}

// Initialize chat when the chatReady event is fired
document.addEventListener('chatReady', () => {
    console.log('Chat ready event received, initializing ChatManager');
    window.initializeChat(); // This creates the WebSocketManager
    window.chatManager = new ChatManager();
});
