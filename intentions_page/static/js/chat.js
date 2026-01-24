// Chat Sidebar Functionality

(function() {
    'use strict';

    // State - default to open on desktop (>=769px) if no saved preference
    const isDesktop = window.innerWidth >= 769;
    const savedState = localStorage.getItem('chatSidebarVisible');
    let chatVisible = savedState !== null ? savedState === 'true' : isDesktop;
    let isLoading = false;
    let showToolConfirmations = true; // Default to showing confirmations

    // DOM elements
    const chatSidebar = document.getElementById('chat-sidebar');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatLoading = document.getElementById('chat-loading');
    const chatIncludeIntentions = document.getElementById('chat-include-intentions');

    if (!chatSidebar) return; // Exit if chat not available (user not logged in)

    // Initialize autosize for chat input
    if (typeof autosize !== 'undefined') {
        autosize(chatInput);
    }

    // Helper function to get toggle button (always fetch fresh from DOM)
    function getChatToggleBtn() {
        return document.getElementById('chat-toggle-btn');
    }

    // Initialize sidebar visibility from saved state
    chatSidebar.setAttribute('data-visible', chatVisible);
    if (chatVisible) {
        const toggleBtn = getChatToggleBtn();
        if (toggleBtn) toggleBtn.classList.add('sidebar-open');
    }

    // Load chat history on page load
    loadChatHistory();

    // Toggle sidebar visibility (works on both desktop and mobile)
    function toggleChat() {
        chatVisible = !chatVisible;
        chatSidebar.setAttribute('data-visible', chatVisible);

        // Update button state (CSS handles icon rotation via transform)
        const toggleBtn = getChatToggleBtn();
        if (chatVisible) {
            if (toggleBtn) toggleBtn.classList.add('sidebar-open');
            chatInput.focus();
        } else {
            if (toggleBtn) toggleBtn.classList.remove('sidebar-open');
        }

        // Save state to localStorage
        localStorage.setItem('chatSidebarVisible', chatVisible);
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
            // Update preference from server (defaults to true if not provided)
            showToolConfirmations = data.show_tool_confirmations ?? true;

            // Clear existing messages (except welcome message)
            const welcome = chatMessages.querySelector('.chat-welcome');
            chatMessages.innerHTML = '';
            if (data.messages.length === 0 && welcome) {
                chatMessages.appendChild(welcome);
            }

            // Add messages
            data.messages.forEach(msg => {
                appendMessage(msg.role, msg.content, false, msg.tool_executions);
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

            // Update preference from server (defaults to true if not provided)
            showToolConfirmations = data.show_tool_confirmations ?? true;

            appendMessage(
                'assistant',
                data.assistant_message.content,
                true,
                data.assistant_message.tool_executions
            );

            scrollToBottom();

            if (data.assistant_message.tool_executions) {
                const hasCreatedIntention = data.assistant_message.tool_executions.some(
                    exec => exec.tool_name === 'create_intention' && exec.success
                );

                const hasReorderedIntentions = data.assistant_message.tool_executions.some(
                    exec => exec.tool_name === 'reorder_intentions' && exec.success
                );

                if (hasCreatedIntention || hasReorderedIntentions) {
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                }
            }
        })
        .catch(error => {
            setLoading(false);
            console.error('Error sending message:', error);
            showError(error.message || 'Failed to send message');
        });
    }

    function appendMessage(role, content, animate = false, toolExecutions = null) {
        const welcome = chatMessages.querySelector('.chat-welcome');
        if (welcome && role !== 'system') {
            welcome.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message chat-message-${role}`;

        if (toolExecutions && toolExecutions.length > 0 && showToolConfirmations) {
            const toolsDiv = document.createElement('div');
            toolsDiv.className = 'chat-tools-used';

            toolExecutions.forEach(exec => {
                const toolBadge = document.createElement('div');
                toolBadge.className = `chat-tool-badge ${exec.success ? 'success' : 'error'}`;

                const icon = exec.success
                    ? '<i class="bi bi-check-circle"></i>'
                    : '<i class="bi bi-x-circle"></i>';

                const toolName = exec.tool_name.replace('_', ' ');
                const resultMessage = exec.success
                    ? (exec.result?.message || 'Success')
                    : (exec.error || 'Failed');

                toolBadge.innerHTML = `
                    ${icon}
                    <span class="tool-name">${toolName}</span>
                    <span class="tool-result">${resultMessage}</span>
                `;

                toolsDiv.appendChild(toolBadge);
            });

            messageDiv.appendChild(toolsDiv);
        }

        let formattedContent;
        if (role === 'assistant' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            const rawHtml = marked.parse(content);
            formattedContent = DOMPurify.sanitize(rawHtml);
        } else {
            formattedContent = content.replace(/\n/g, '<br>');
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'chat-message-content';
        contentDiv.innerHTML = formattedContent;
        messageDiv.appendChild(contentDiv);

        if (animate) {
            messageDiv.style.opacity = '0';
            messageDiv.style.transform = 'translateY(10px)';
        }

        chatMessages.appendChild(messageDiv);

        if (animate) {
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
        const sendBtn = document.getElementById('chat-send-btn');
        if (sendBtn) sendBtn.disabled = loading;
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

    // Event listeners using event delegation for buttons that may be replaced
    document.addEventListener('click', function(e) {
        // Toggle button
        if (e.target.closest('#chat-toggle-btn')) {
            e.preventDefault();
            toggleChat();
            return;
        }

        // Close button
        if (e.target.closest('#chat-close-btn')) {
            e.preventDefault();
            toggleChat();
            return;
        }

        // Send button
        if (e.target.closest('#chat-send-btn')) {
            e.preventDefault();
            sendMessage();
            return;
        }

        // Clear button
        if (e.target.closest('#chat-clear-btn')) {
            e.preventDefault();
            clearChatHistory();
            return;
        }
    });

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
