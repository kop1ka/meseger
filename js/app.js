/**
 * CYBER//MESSENGER CLIENT APPLICATION
 * Cyberpunk themed neural link interface
 * Uses vanilla JavaScript with modern ES6+ features
 */

class MessengerApp {
    constructor() {
        this.ws = null;
        this.username = '';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        
        // DOM Elements
        this.elements = {
            loginModal: document.getElementById('loginModal'),
            usernameInput: document.getElementById('usernameInput'),
            joinButton: document.querySelector('.login-box button'),
            container: document.querySelector('.container'),
            usersList: document.getElementById('usersList'),
            userCount: document.getElementById('userCount'),
            status: document.getElementById('status'),
            messages: document.getElementById('messages'),
            messageInput: document.getElementById('messageInput'),
            sendButton: document.getElementById('sendBtn'),
            timeDisplay: document.getElementById('timeDisplay')
        };
        
        this.init();
        this.startTimeDisplay();
    }
    
    init() {
        this.bindEvents();
        this.setupMobileOptimizations();
        this.setupCyberEffects();
    }
    
    setupCyberEffects() {
        // Add glitch effect on hover for buttons
        const cyberButtons = document.querySelectorAll('#sendBtn, .login-box button');
        cyberButtons.forEach(btn => {
            btn.addEventListener('mouseenter', () => {
                btn.style.animation = 'glitch-1 0.3s infinite';
            });
            btn.addEventListener('mouseleave', () => {
                btn.style.animation = '';
            });
        });
    }
    
    startTimeDisplay() {
        if (this.elements.timeDisplay) {
            const updateTime = () => {
                const now = new Date();
                const timeStr = now.toLocaleTimeString('en-US', { 
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
                this.elements.timeDisplay.textContent = timeStr;
            };
            updateTime();
            setInterval(updateTime, 1000);
        }
    }
    
    bindEvents() {
        // Login
        if (this.elements.joinButton) {
            this.elements.joinButton.addEventListener('click', () => this.joinChat());
        }
        
        if (this.elements.usernameInput) {
            this.elements.usernameInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.joinChat();
                }
            });
        }
        
        // Send message
        if (this.elements.sendButton) {
            this.elements.sendButton.addEventListener('click', () => this.sendMessage());
        }
        
        if (this.elements.messageInput) {
            this.elements.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.sendMessage();
                }
            });
            
            // Auto-resize input on mobile
            this.elements.messageInput.addEventListener('input', () => {
                this.adjustInputHeight();
            });
        }
        
        // Handle visibility change (mobile optimization)
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('App hidden - pause updates');
            } else {
                console.log('App visible - resume updates');
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.scrollToBottom();
                }
            }
        });
        
        // Handle online/offline status
        window.addEventListener('online', () => this.handleOnlineStatus());
        window.addEventListener('offline', () => this.handleOfflineStatus());
    }
    
    setupMobileOptimizations() {
        // Prevent zoom on double tap for iOS
        document.addEventListener('dblclick', (e) => {
            e.preventDefault();
        }, { passive: false });
        
        // Add touch feedback for buttons
        const buttons = document.querySelectorAll('button');
        buttons.forEach(button => {
            button.addEventListener('touchstart', function() {
                this.style.transform = 'scale(0.98)';
            });
            
            button.addEventListener('touchend', function() {
                this.style.transform = '';
            });
        });
        
        // Optimize viewport for mobile
        this.setViewportHeight();
        window.addEventListener('resize', () => this.setViewportHeight());
    }
    
    setViewportHeight() {
        // Fix for mobile browsers with dynamic UI
        let vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }
    
    adjustInputHeight() {
        const input = this.elements.messageInput;
        if (!input) return;
        
        input.style.height = 'auto';
        const newHeight = Math.min(input.scrollHeight, 120);
        input.style.height = `${newHeight}px`;
    }
    
    joinChat() {
        const input = this.elements.usernameInput;
        if (!input) return;
        
        this.username = input.value.trim();
        
        if (!this.username) {
            this.showAlert('Please enter a username', 'error');
            return;
        }
        
        // Validate username
        if (this.username.length < 2 || this.username.length > 20) {
            this.showAlert('Username must be 2-20 characters', 'error');
            return;
        }
        
        // Connect to WebSocket server
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.hostname}:8765`;
        
        this.connectWebSocket(wsUrl);
    }
    
    connectWebSocket(wsUrl) {
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('Connected to server');
                this.reconnectAttempts = 0;
                
                // Hide login modal
                if (this.elements.loginModal) {
                    this.elements.loginModal.classList.add('hidden');
                }
                
                // Update status
                this.updateStatus('Connected', 'connected');
                
                // Send join message
                this.sendToServer({
                    action: 'join',
                    username: this.username
                });
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.displayMessage(data);
                } catch (e) {
                    console.error('Error parsing message:', e);
                }
            };
            
            this.ws.onclose = () => {
                console.log('Disconnected from server');
                this.updateStatus('Disconnected - Reconnecting...', 'disconnected');
                this.attemptReconnect(wsUrl);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
        } catch (e) {
            console.error('Failed to create WebSocket:', e);
            this.showAlert('Connection failed. Please refresh the page.', 'error');
        }
    }
    
    attemptReconnect(wsUrl) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.showAlert('Unable to connect. Please refresh the page.', 'error');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            if (this.ws && this.ws.readyState !== WebSocket.OPEN) {
                this.connectWebSocket(wsUrl);
            }
        }, delay);
    }
    
    sendToServer(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected');
        }
    }
    
    sendMessage() {
        const input = this.elements.messageInput;
        if (!input) return;
        
        const message = input.value.trim();
        
        if (!message) {
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.showAlert('Not connected to server', 'error');
            return;
        }
        
        this.sendToServer({
            action: 'message',
            message: message
        });
        
        input.value = '';
        input.style.height = 'auto';
        input.focus();
    }
    
    displayMessage(data) {
        if (!this.elements.messages) return;
        
        const msgDiv = document.createElement('div');
        
        if (data.type === 'system') {
            msgDiv.className = 'message system';
            msgDiv.innerHTML = `<span class="system-prefix">>>></span>${this.escapeHtml(data.message)}<span class="system-suffix"><<<</span>`;
            
            if (data.users) {
                if (this.elements.usersList) {
                    this.elements.usersList.innerHTML = `<span class="label">[</span>CONNECTED_NETRUNNERS<span class="label">]:</span> <span id="userCount">${data.users.length}</span>`;
                    this.elements.userCount = document.getElementById('userCount');
                }
            }
        } else if (data.type === 'chat') {
            const isMyMessage = data.username === this.username;
            msgDiv.className = `message chat ${isMyMessage ? 'my-message' : ''}`;
            
            const timeString = data.timestamp 
                ? new Date(data.timestamp).toLocaleTimeString()
                : new Date().toLocaleTimeString();
            
            msgDiv.innerHTML = `
                <div class="message-username">${this.escapeHtml(data.username)}</div>
                <div class="message-text">${this.escapeHtml(data.message)}</div>
                <div class="message-time">${timeString}</div>
            `;
        }
        
        this.elements.messages.appendChild(msgDiv);
        this.scrollToBottom();
    }
    
    scrollToBottom() {
        if (!this.elements.messages) return;
        
        // Smooth scroll for better UX
        this.elements.messages.scrollTo({
            top: this.elements.messages.scrollHeight,
            behavior: 'smooth'
        });
    }
    
    updateStatus(text, className) {
        if (!this.elements.status) return;
        
        this.elements.status.textContent = text;
        this.elements.status.className = `status ${className}`;
    }
    
    handleOnlineStatus() {
        console.log('Network online');
        this.updateStatus('Reconnecting...', 'disconnected');
        // Attempt to reconnect
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.hostname}:8765`;
        this.attemptReconnect(wsUrl);
    }
    
    handleOfflineStatus() {
        console.log('Network offline');
        this.updateStatus('No internet connection', 'disconnected');
    }
    
    showAlert(message, type = 'info') {
        // Simple alert replacement with custom styling
        const alertDiv = document.createElement('div');
        alertDiv.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: ${type === 'error' ? '#f44336' : '#2196F3'};
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 2000;
            font-size: 14px;
            animation: slideDown 0.3s ease;
        `;
        alertDiv.textContent = message;
        
        // Add animation keyframes
        if (!document.getElementById('alert-styles')) {
            const style = document.createElement('style');
            style.id = 'alert-styles';
            style.textContent = `
                @keyframes slideDown {
                    from { opacity: 0; transform: translateX(-50%) translateY(-20px); }
                    to { opacity: 1; transform: translateX(-50%) translateY(0); }
                }
                @keyframes slideUp {
                    from { opacity: 1; transform: translateX(-50%) translateY(0); }
                    to { opacity: 0; transform: translateX(-50%) translateY(-20px); }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.style.animation = 'slideUp 0.3s ease';
            setTimeout(() => alertDiv.remove(), 300);
        }, 3000);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.messengerApp = new MessengerApp();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.messengerApp) {
        window.messengerApp.disconnect();
    }
});
