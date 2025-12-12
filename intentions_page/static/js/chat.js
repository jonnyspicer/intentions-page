// Chat Sidebar Functionality

(function() {
    'use strict';

    // State
    let chatVisible = false;
    let isLoading = false;

    // DOM elements
    const chatSidebar = document.getElementById('chat-sidebar');
    const chatToggleBtn = document.getElementById('chat-toggle-btn');
    const chatCloseBtn = document.getElementById('chat-close-btn');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const chatClearBtn = document.getElementById('chat-clear-btn');
    const chatLoading = document.getElementById('chat-loading');
    const chatIncludeIntentions = document.getElementById('chat-include-intentions');

    if (!chatSidebar) return; // Exit if chat not available (user not logged in)

    // Initialize autosize for chat input
    if (typeof autosize !== 'undefined') {
        autosize(chatInput);
    }

    // Load chat history on page load
    loadChatHistory();

    // Toggle sidebar visibility (primarily for mobile)
    function toggleChat() {
        chatVisible = !chatVisible;
        chatSidebar.setAttribute('data-visible', chatVisible);

        if (chatVisible) {
            chatInput.focus();
        }
    }

    // Load chat history from server
    function loadChatHistory() {
        fetch('/chat/history', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            // Clear existing messages (except welcome message)
            const welcome = chatMessages.querySelector('.chat-welcome');
            chatMessages.innerHTML = '';
            if (data.messages.length === 0 && welcome) {
                chatMessages.appendChild(welcome);
            }

            // Add messages
            data.messages.forEach(msg => {
                appendMessage(msg.role, msg.content, false);
            });

            scrollToBottom();
        })
        .catch(error => {
            console.error('Error loading chat history:', error);
            showError('Failed to load chat history');
        });
    }

    // Send message to server
    function sendMessage() {
        const message = chatInput.value.trim();

        if (!message || isLoading) return;

        // Clear input
        chatInput.value = '';

        // Reset textarea height after clearing
        if (typeof autosize !== 'undefined') {
            autosize.update(chatInput);
        }

        // Show user message immediately
        appendMessage('user', message, true);

        // Show loading
        setLoading(true);

        // Get CSRF token
        const csrfToken = getCsrfToken();

        // Send to server
        fetch('/chat/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                message: message,
                include_intentions: chatIncludeIntentions.checked
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Request failed');
                });
            }
            return response.json();
        })
        .then(data => {
            setLoading(false);

            // Assistant response
            appendMessage('assistant', data.assistant_message.content, true);

            scrollToBottom();
        })
        .catch(error => {
            setLoading(false);
            console.error('Error sending message:', error);
            showError(error.message || 'Failed to send message');
        });
    }

    // Append message to chat
    function appendMessage(role, content, animate = false) {
        // Remove welcome message when first real message appears
        const welcome = chatMessages.querySelector('.chat-welcome');
        if (welcome && role !== 'system') {
            welcome.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message chat-message-${role}`;

        // Format content - render markdown for assistant messages, plain text for others
        let formattedContent;
        if (role === 'assistant' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            // Parse markdown and sanitize HTML
            const rawHtml = marked.parse(content);
            formattedContent = DOMPurify.sanitize(rawHtml);
        } else {
            // For user and system messages, just preserve line breaks
            formattedContent = content.replace(/\n/g, '<br>');
        }
        messageDiv.innerHTML = formattedContent;

        if (animate) {
            messageDiv.style.opacity = '0';
            messageDiv.style.transform = 'translateY(10px)';
        }

        chatMessages.appendChild(messageDiv);

        if (animate) {
            // Trigger animation
            setTimeout(() => {
                messageDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                messageDiv.style.opacity = '1';
                messageDiv.style.transform = 'translateY(0)';
            }, 10);
        }

        scrollToBottom();
    }

    // Show error message
    function showError(message) {
        appendMessage('system', `Error: ${message}`, true);
    }

    // Set loading state
    function setLoading(loading) {
        isLoading = loading;
        chatLoading.style.display = loading ? 'flex' : 'none';
        chatSendBtn.disabled = loading;
        chatInput.disabled = loading;

        if (loading) {
            scrollToBottom();
        }
    }

    // Scroll to bottom of messages
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Clear chat history
    function clearChatHistory() {
        if (!confirm('Are you sure you want to clear your chat history? This cannot be undone.')) {
            return;
        }

        const csrfToken = getCsrfToken();

        fetch('/chat/clear', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            // Clear UI
            chatMessages.innerHTML = '<div class="chat-welcome"><p>Chat history cleared.</p></div>';
            appendMessage('system', `Deleted ${data.deleted_count} messages.`, true);
        })
        .catch(error => {
            console.error('Error clearing history:', error);
            showError('Failed to clear chat history');
        });
    }

    // Get CSRF token from meta tag
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    }

    // Event listeners
    chatToggleBtn.addEventListener('click', toggleChat);
    chatCloseBtn.addEventListener('click', toggleChat);
    chatSendBtn.addEventListener('click', sendMessage);
    chatClearBtn.addEventListener('click', clearChatHistory);

    // Send on Enter (but Shift+Enter for new line)
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Keyboard shortcut: 'c' to toggle chat
    Mousetrap.bind('c', function(e) {
        toggleChat();
        e.preventDefault();
    });

    // Close chat on Escape when sidebar is open
    Mousetrap.bind('esc', function(e) {
        if (chatVisible) {
            toggleChat();
            e.preventDefault();
        }
    });

})();
