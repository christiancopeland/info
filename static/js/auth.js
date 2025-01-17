class AuthManager {
    constructor() {
        this.isAuthenticated = false;
        this.user = null;
        this.loginModal = document.getElementById('loginModal');
        
        // Wait for DOM to be fully loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.checkAuthentication();
                this.setupEventListeners();
            });
        } else {
            this.checkAuthentication();
            this.setupEventListeners();
        }
    }

    setupEventListeners() {
        // Handle the update API key button in sidebar
        const updateButton = document.getElementById('updateApiKey');
        if (updateButton) {
            updateButton.addEventListener('click', () => this.showLoginPrompt());
        }

        // Handle login/register forms
        const loginForm = document.getElementById('loginForm');
        const registerForm = document.getElementById('registerForm');
        
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }
        if (registerForm) {
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
        }
    }

    async handleLogin(event) {
        event.preventDefault();
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;

        try {
            console.log('Starting login request...');
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    'username': email,
                    'password': password,
                }),
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();
                console.log('Login response:', data);
                
                // Wait a brief moment to ensure cookie is set
                await new Promise(resolve => setTimeout(resolve, 100));
                
                // Verify the cookie is set before proceeding
                const verifyResponse = await fetch('/api/auth/verify', {
                    credentials: 'include'
                });
                
                if (verifyResponse.ok) {
                    this.isAuthenticated = true;
                    this.updateAuthStatus('Logged in successfully');
                    this.hideLoginModal();
                    
                    // Only dispatch auth state changed after verification
                    document.dispatchEvent(new Event('authStateChanged'));
                    
                    // Check if API key is needed
                    if (!data.has_api_key) {
                        const apiKey = await this.promptForApiKey();
                        if (apiKey) {
                            await this.submitApiKey(apiKey);
                        }
                    }
                } else {
                    throw new Error('Authentication verification failed');
                }
            } else {
                const error = await response.json();
                this.updateAuthStatus(error.detail || 'Login failed');
            }
        } catch (error) {
            console.error('Login error:', error);
            this.updateAuthStatus('Login failed');
        }
    }

    async handleRegister(event) {
        event.preventDefault();
        const email = document.getElementById('registerEmail').value;
        const password = document.getElementById('registerPassword').value;

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email, password }),
            });

            if (response.ok) {
                this.updateAuthStatus('Registration successful. Please log in.');
                // Switch to login form
                document.getElementById('registerModal').style.display = 'none';
                document.getElementById('loginModal').style.display = 'block';
            } else {
                const error = await response.json();
                this.updateAuthStatus(error.detail || 'Registration failed');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.updateAuthStatus('Registration failed');
        }
    }

    async showLoginPrompt() {
        const apiKey = await this.promptForApiKey();
        if (apiKey) {
            try {
                await this.submitApiKey(apiKey);
            } catch (error) {
                console.error('Failed to update API key:', error);
                this.updateApiKeyStatus('Failed to update API key');
            }
        }
    }

    async checkAuthentication() {
        console.log('Checking authentication...');
        try {
            const response = await fetch('/api/auth/verify', {
                credentials: 'include'
            });
            
            if (response.ok) {
                console.log('Authentication verified');
                this.isAuthenticated = true;
                this.hideLoginModal();
                
                // Dispatch auth state changed event
                document.dispatchEvent(new Event('authStateChanged'));
                return true;
            } else {
                console.log('Not authenticated');
                this.clearAuth();
            }
        } catch (error) {
            console.error('Auth check failed:', error);
            this.clearAuth();
        }
        return false;
    }

    async promptForApiKey() {
        return new Promise((resolve) => {
            const modal = document.getElementById('apiKeyModal');
            const input = document.getElementById('apiKeyInput');
            const saveButton = document.getElementById('saveApiKey');
            const cancelButton = document.getElementById('cancelApiKey');

            // Show the modal
            modal.style.display = 'block';

            // Handle save button click
            const handleSave = () => {
                const apiKey = input.value.trim();
                modal.style.display = 'none';
                input.value = '';
                cleanup();
                resolve(apiKey);
            };

            // Handle cancel button click
            const handleCancel = () => {
                modal.style.display = 'none';
                input.value = '';
                cleanup();
                resolve(null);
            };

            // Clean up event listeners
            const cleanup = () => {
                saveButton.removeEventListener('click', handleSave);
                cancelButton.removeEventListener('click', handleCancel);
            };

            // Add event listeners
            saveButton.addEventListener('click', handleSave);
            cancelButton.addEventListener('click', handleCancel);
        });
    }

    setToken(token) {
        console.log('Setting token:', token); // Debug log
        this.token = token;
    }

    clearToken() {
        this.token = null;
    }

    showLoginModal() {
        if (this.loginModal) {
            this.loginModal.style.display = 'block';
        }
    }

    updateApiKeyStatus(message) {
        const statusElement = document.getElementById('apiKeyStatus');
        if (statusElement) {
            statusElement.textContent = message;
        }
    }

    updateAuthStatus(message) {
        const statusElement = document.getElementById('authStatus');
        if (statusElement) {
            statusElement.textContent = message;
        }
    }

    async submitApiKey(apiKey) {
        try {
            const response = await fetch('/api/auth/key', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({ api_key: apiKey })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Invalid API key');
            }

            const data = await response.json();
            this.isAuthenticated = true;
            this.updateApiKeyStatus('API key is valid');
        } catch (error) {
            console.error('API key submission failed:', error);
            this.updateApiKeyStatus('API key is invalid');
            throw error;
        }
    }

    parseCookies() {
        return document.cookie
            .split(';')
            .map(cookie => cookie.trim())
            .reduce((acc, cookie) => {
                if (cookie) {
                    const [key, value] = cookie.split('=');
                    acc[key] = value;
                }
                return acc;
            }, {});
    }

    getAuthHeaders() {
        const token = sessionStorage.getItem('auth_token');
        console.log('Getting auth headers, token:', token);
        
        return token ? {
            'Authorization': `Bearer ${token}`
        } : {};
    }

    // Helper method to get specific cookie
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    clearAuth() {
        this.isAuthenticated = false;
        this.showLoginModal();
        
        // Clear the cookie by making a logout request
        fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'include'
        }).then(() => {
            // Dispatch auth state changed event
            document.dispatchEvent(new Event('authStateChanged'));
        });
    }

    hideLoginModal() {
        if (this.loginModal) {
            this.loginModal.style.display = 'none';
        }
    }

    initializeChatWhenReady() {
        console.log('Waiting for chat container...');
        const maxAttempts = 10;
        let attempts = 0;

        const checkAndInitialize = () => {
            const chatContainer = document.getElementById('chat-messages');
            if (chatContainer) {
                console.log('Chat container found, initializing chat...');
                if (typeof window.initializeChat === 'function') {
                    window.initializeChat();
                } else {
                    console.error('Chat initialization function not found');
                }
                return true;
            }
            
            attempts++;
            if (attempts < maxAttempts) {
                console.log(`Chat container not found, attempt ${attempts}/${maxAttempts}`);
                setTimeout(checkAndInitialize, 500);
            } else {
                console.error('Failed to find chat container after maximum attempts');
            }
            return false;
        };

        // Start checking
        checkAndInitialize();
    }
}

// Initialize auth manager
console.log('Initializing AuthManager');
window.authManager = new AuthManager(); 