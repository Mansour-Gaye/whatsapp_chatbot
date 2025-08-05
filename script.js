/**
 * Chatbox AI Assistant
 *
 * Ce script gère l'ensemble de la logique pour une chatbox web moderne,
 * personnalisable et persistante.
 */
document.addEventListener('DOMContentLoaded', () => {
    // ---------------------------
    //  CONFIGURATION PAR DEFAUT
    // ---------------------------
    const defaultConfig = {
        position: 'bottom-right', // ou 'bottom-left'
        mode: 'floating',         // ou 'fullscreen'
        assetBasePath: '',        // ex: '/static/img/chatbot/'
        theme: {
            primary: '#007bff',
            userMessageBg: '#007bff',
        },
        header: {
            title: 'Assistant IA',
            botAvatar: 'https://via.placeholder.com/40'
        },
        welcomeMessage: 'Bonjour ! Comment puis-je vous aider aujourd\'hui ?',
        initialQuickReplies: ['Info produit', 'Support technique', 'Autre question']
    };

    // ---------------------------
    //  VARIABLES GLOBALES & ELEMENTS DU DOM
    // ---------------------------
    const chatboxContainer = document.getElementById('chatbox-container');
    const chatboxMessages = document.getElementById('chatbox-messages');
    const chatboxForm = document.getElementById('chatbox-form');
    const chatboxInput = document.getElementById('chatbox-input');
    const closeChatboxBtn = document.getElementById('close-chatbox');
    const chatLauncher = document.getElementById('chat-launcher');

    let chatHistory = [];
    let config = {};

    // =================================================================================
    //  FONCTIONS DE RENDU (Construction de l'interface)
    // =================================================================================

    function renderQuickReplies(replies) {
        const container = document.createElement('div');
        container.classList.add('quick-replies-container');
        replies.forEach(replyText => {
            const button = document.createElement('button');
            button.classList.add('quick-reply-btn');
            button.textContent = replyText;
            button.addEventListener('click', () => handleQuickReplyClick(replyText));
            container.appendChild(button);
        });
        chatboxMessages.appendChild(container);
    }

    function createCard(cardData) {
        const cardContainer = document.createElement('div');
        cardContainer.classList.add('card-container');

        if (cardData.imageUrl) {
            const img = document.createElement('img');
            // Préfixe l'URL de l'image avec la base si elle est relative
            if (cardData.imageUrl.startsWith('/')) {
                 img.src = `${config.assetBasePath}${cardData.imageUrl}`;
            } else {
                 img.src = cardData.imageUrl;
            }
            img.alt = cardData.title || 'Card Image';
            cardContainer.appendChild(img);
        }
        const cardBody = document.createElement('div');
        cardBody.classList.add('card-body');
        if (cardData.title) {
            const title = document.createElement('div');
            title.classList.add('card-title');
            title.textContent = cardData.title;
            cardBody.appendChild(title);
        }
        if (cardData.subtitle) {
            const subtitle = document.createElement('div');
            subtitle.classList.add('card-subtitle');
            subtitle.textContent = cardData.subtitle;
            cardBody.appendChild(subtitle);
        }
        if (cardData.buttons) {
            cardData.buttons.forEach(btnData => {
                const button = document.createElement('a');
                button.classList.add('card-button');
                button.textContent = btnData.title;
                button.href = btnData.url || '#';
                if (btnData.url) button.target = '_blank';
                cardBody.appendChild(button);
            });
        }
        cardContainer.appendChild(cardBody);
        return cardContainer;
    }

    function renderMessage(messageData) {
        const { text, sender, timestamp, options = {}, isHistory } = messageData;

        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) typingIndicator.remove();

        const messageBubble = document.createElement('div');
        messageBubble.classList.add('message-bubble', sender);

        if (text) {
            const messageContent = document.createElement('div');
            messageContent.classList.add('message-content');
            messageContent.textContent = text;
            messageBubble.appendChild(messageContent);
        }

        if (options.card) {
            messageBubble.appendChild(createCard(options.card));
        }

        const messageFooter = document.createElement('div');
        messageFooter.classList.add('message-footer');

        const time = new Date(timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        const timestampEl = document.createElement('div');
        timestampEl.classList.add('message-timestamp');
        timestampEl.textContent = time;
        messageFooter.appendChild(timestampEl);

        if (sender === 'user') {
            const readReceipt = document.createElement('span');
            readReceipt.classList.add('read-receipt', 'seen');
            readReceipt.innerHTML = '✓✓';
            messageFooter.appendChild(readReceipt);
        }

        messageBubble.appendChild(messageFooter);
        chatboxMessages.appendChild(messageBubble);

        if (!isHistory && options.quickReplies && options.quickReplies.length > 0) {
            renderQuickReplies(options.quickReplies);
        }
    }

    // =================================================================================
    //  FONCTIONS DE LOGIQUE (Gestion des actions)
    // =================================================================================

    function addMessage(text, sender, options = {}) {
        const messageData = { text, sender, timestamp: Date.now(), options };
        chatHistory.push(messageData);
        saveHistory();
        renderMessage(messageData);
        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;
    }

    function simulateBotResponse(userMessage) {
        toggleTypingIndicator(true);
        chatboxInput.disabled = true;

        setTimeout(() => {
            toggleTypingIndicator(false);
            let botReply = '';
            let options = {};
            const lowerUserMessage = userMessage.toLowerCase();

            if (lowerUserMessage.includes('produit')) {
                botReply = 'Voici notre produit phare, le "Chatbot Pro".';
                options.card = { imageUrl: 'https://via.placeholder.com/300x150/5A3E8A/white?text=Produit', title: 'Chatbot Pro', subtitle: 'La solution d\'IA pour votre entreprise.', buttons: [{ title: 'Voir les détails', url: '#' }] };
                options.quickReplies = ['Quel est le prix ?', 'Support technique'];
            } else {
                botReply = `J'ai bien reçu votre message : "${userMessage}".`;
                options.quickReplies = ['Info produit', 'Info services'];
            }

            addMessage(botReply, 'bot', options);
            chatboxInput.disabled = false;
            chatboxInput.focus();
        }, 1500);
    }

    function handleQuickReplyClick(text) {
        const qrContainers = document.querySelectorAll('.quick-replies-container');
        qrContainers.forEach(container => container.remove());
        addMessage(text, 'user');
        simulateBotResponse(text);
    }

    function toggleTypingIndicator(show) {
        let existingIndicator = document.getElementById('typing-indicator');
        if (existingIndicator) existingIndicator.remove();
        if (show) {
            const indicator = document.createElement('div');
            indicator.id = 'typing-indicator';
            indicator.classList.add('message-bubble', 'bot', 'typing-indicator');
            indicator.innerHTML = '<span></span><span></span><span></span>';
            chatboxMessages.appendChild(indicator);
            chatboxMessages.scrollTop = chatboxMessages.scrollHeight;
        }
    }

    function toggleChatbox() {
        chatboxContainer.classList.toggle('open');
    }

    // =================================================================================
    //  PERSISTANCE & CONFIGURATION
    // =================================================================================

    function saveHistory() {
        localStorage.setItem('chatbox-history', JSON.stringify(chatHistory));
    }

    function loadHistory() {
        const savedHistory = localStorage.getItem('chatbox-history');
        if (savedHistory) {
            chatHistory = JSON.parse(savedHistory);
            chatHistory.forEach(messageData => renderMessage({ ...messageData, isHistory: true }));
            return true;
        }
        return false;
    }

    function applyConfig(config) {
        const root = document.documentElement;
        root.style.setProperty('--primary-accent-color', config.theme.primary);
        root.style.setProperty('--user-message-background', config.theme.userMessageBg);

        const launcher = document.getElementById('chat-launcher');
        if (config.position === 'bottom-left') {
            chatboxContainer.style.left = 'calc(var(--spacing-unit) * 3)';
            chatboxContainer.style.right = 'auto';
            launcher.style.left = 'calc(var(--spacing-unit) * 3)';
            launcher.style.right = 'auto';
        }

        if (config.mode === 'fullscreen') {
            chatboxContainer.classList.add('fullscreen');
        }

        document.querySelector('.chatbox-header-title').textContent = config.header.title;

        // Applique le chemin de base à l'avatar
        let avatarSrc = config.header.botAvatar;
        if (avatarSrc && !avatarSrc.startsWith('http')) {
            avatarSrc = `${config.assetBasePath}${avatarSrc}`;
        }
        document.getElementById('bot-avatar').src = avatarSrc;
    }

    function loadConfig() {
        let finalConfig = JSON.parse(JSON.stringify(defaultConfig));

        // Priorité 1: Paramètres URL
        const urlParams = new URLSearchParams(window.location.search);
        const urlConfig = {
            theme: {},
            header: {}
        };
        if (urlParams.get('primaryColor')) {
            const color = '#' + urlParams.get('primaryColor');
            urlConfig.theme.primary = color;
            urlConfig.theme.userMessageBg = color;
        }
        if (urlParams.get('position')) urlConfig.position = urlParams.get('position');
        if (urlParams.get('title')) urlConfig.header.title = urlParams.get('title');
        if (urlParams.get('avatar')) urlConfig.header.botAvatar = urlParams.get('avatar');
        if (urlParams.get('basePath')) urlConfig.assetBasePath = urlParams.get('basePath');

        // Fusionne la config URL avec la config par défaut
        finalConfig.theme = { ...finalConfig.theme, ...urlConfig.theme };
        finalConfig.header = { ...finalConfig.header, ...urlConfig.header };
        delete urlConfig.theme;
        delete urlConfig.header;
        finalConfig = { ...finalConfig, ...urlConfig };

        return finalConfig;
    }

    // =================================================================================
    //  INITIALISATION
    // =================================================================================

    function init() {
        config = loadConfig();
        applyConfig(config);

        chatLauncher.addEventListener('click', toggleChatbox);
        closeChatboxBtn.addEventListener('click', toggleChatbox);

        const historyLoaded = loadHistory();
        if (!historyLoaded) {
            addMessage(config.welcomeMessage, 'bot', {
                quickReplies: config.initialQuickReplies
            });
        }
        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;

        chatboxForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const messageText = chatboxInput.value.trim();
            if (messageText) {
                const qrContainers = document.querySelectorAll('.quick-replies-container');
                qrContainers.forEach(container => container.remove());
                addMessage(messageText, 'user');
                chatboxInput.value = '';
                simulateBotResponse(messageText);
            }
        });
    }

    init();
});
