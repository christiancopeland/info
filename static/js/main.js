console.log('main.js loaded');

// Create a custom event for when chat is ready to initialize
const chatReadyEvent = new Event('chatReady');

// Define initializeChat for backward compatibility
window.initializeChat = function() {
    console.log('Initializing chat...');
    
    try {
        console.log('Creating WebSocket manager');
        window.wsManager = new WebSocketManager();
        console.log('Chat initialization complete');
    } catch (error) {
        console.error('Error during chat initialization:', error);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded - dispatching chatReady event');
    document.dispatchEvent(chatReadyEvent);
});
