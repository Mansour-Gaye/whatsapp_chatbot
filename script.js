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
    const API_ENDPOINT = '/api/chat';
    const LEAD_ENDPOINT = '/api/lead';

    const chatboxContainer = document.getElementById('chatbox-container');
    const chatboxMessages = document.getElementById('chatbox-messages');
    const chatboxForm = document.getElementById('chatbox-form');
    const chatboxInput = document.getElementById('chatbox-input');
    const closeChatboxBtn = document.getElementById('close-chatbox');
    const chatLauncher = document.getElementById('chat-launcher');

    let config = {};
    let chatHistory = []; // Pour affichage et persistance localStorage

    // État du chat pour la logique métier
    let step = 0; // 0: chat libre, 1: collecte infos, 2: chat normal après collecte
    let exchangeCount = 0;
    let lead = { name: "", email: "", phone: "" };
    let missingFields = [];


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
        // Le rôle pour l'API est 'assistant', mais pour l'UI c'est 'bot'
        const role = (sender === 'bot') ? 'assistant' : 'user';
        const messageData = { text, sender, role, timestamp: Date.now(), options };

        chatHistory.push(messageData);
        saveHistory();
        renderMessage(messageData);
        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;
    }

    function isDefaultValue(value) {
        return value === "1234567890" || (value && value.endsWith("@example.com"));
    }

    function checkMissingFields() {
        missingFields = [];
        if (!lead.name || lead.name.trim() === "") missingFields.push('nom');
        if (!lead.email || isDefaultValue(lead.email)) missingFields.push('email');
        if (!lead.phone || isDefaultValue(lead.phone)) missingFields.push('téléphone');
        return missingFields.length > 0;
    }

    function getMissingFieldsMessage() {
        if (missingFields.length === 1) {
            return `Pourriez-vous me donner votre ${missingFields[0]} ?`;
        } else if (missingFields.length === 2) {
            return `Pourriez-vous me donner votre ${missingFields[0]} et votre ${missingFields[1]} ?`;
        } else {
            return `Pourriez-vous me donner votre ${missingFields[0]}, votre ${missingFields[1]} et votre ${missingFields[2]} ?`;
        }
    }

    async function handleUserMessage(userMessage) {
        toggleTypingIndicator(true);
        chatboxInput.disabled = true;

        // Prépare l'historique pour l'API
        const historyForApi = chatHistory.map(msg => ({
            role: msg.role,
            content: msg.text
        }));

        try {
            let response;
            let data;

            if (step === 0) {
                exchangeCount++;
                response = await fetch(API_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ history: historyForApi }),
                });
                if (!response.ok) throw new Error('Erreur réseau API_ENDPOINT');
                data = await response.json();

                addMessage(data.response, 'bot');

                if (exchangeCount >= 2) {
                    step = 1;
                    setTimeout(() => {
                        addMessage('Au fait, pour mieux vous aider, puis-je connaître votre nom, email et téléphone ?', 'bot');
                    }, 1000);
                }
            } else if (step === 1) {
                response = await fetch(LEAD_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input: userMessage, lead: lead }),
                });
                if (!response.ok) throw new Error('Erreur réseau LEAD_ENDPOINT');
                data = await response.json();

                if (data.lead) {
                    if (data.lead.name && !isDefaultValue(data.lead.name)) lead.name = data.lead.name;
                    if (data.lead.email && !isDefaultValue(data.lead.email)) lead.email = data.lead.email;
                    if (data.lead.phone && !isDefaultValue(data.lead.phone)) lead.phone = data.lead.phone;
                }

                if (checkMissingFields()) {
                    addMessage(getMissingFieldsMessage(), 'bot');
                } else {
                    await fetch(LEAD_ENDPOINT, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ input: userMessage, lead: lead, save: true }),
                    });
                    addMessage('Merci, vos informations ont bien été enregistrées !', 'bot');
                    step = 2; // Passe au chat normal
                }
            } else { // step === 2
                response = await fetch(API_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ history: historyForApi }),
                });
                if (!response.ok) throw new Error('Erreur réseau API_ENDPOINT (step 2)');
                data = await response.json();
                addMessage(data.response, 'bot');
            }
        } catch (error) {
            console.error('Erreur:', error);
            addMessage('Désolé, une erreur est survenue. Veuillez réessayer.', 'bot');
        } finally {
            toggleTypingIndicator(false);
            chatboxInput.disabled = false;
            chatboxInput.focus();
        }
    }

    function handleQuickReplyClick(text) {
        const qrContainers = document.querySelectorAll('.quick-replies-container');
        qrContainers.forEach(container => container.remove());
        addMessage(text, 'user');
        handleUserMessage(text);
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

    function deepMerge(target, source) {
        const output = { ...target };
        if (isObject(target) && isObject(source)) {
            Object.keys(source).forEach(key => {
                if (isObject(source[key])) {
                    if (!(key in target)) {
                        Object.assign(output, { [key]: source[key] });
                    } else {
                        output[key] = deepMerge(target[key], source[key]);
                    }
                } else {
                    Object.assign(output, { [key]: source[key] });
                }
            });
        }
        return output;
    }
    const isObject = (item) => (item && typeof item === 'object' && !Array.isArray(item));

    function loadConfig() {
        // Priorité 3: defaultConfig
        let finalConfig = JSON.parse(JSON.stringify(defaultConfig));

        // Priorité 2: window.chatboxConfig
        if (window.chatboxConfig) {
            finalConfig = deepMerge(finalConfig, window.chatboxConfig);
        }

        // Priorité 1: Paramètres URL
        const urlParams = new URLSearchParams(window.location.search);
        const urlConfig = { theme: {}, header: {} };

        if (urlParams.get('primaryColor')) {
            const color = '#' + urlParams.get('primaryColor');
            urlConfig.theme.primary = color;
            urlConfig.theme.userMessageBg = color;
        }
        if (urlParams.get('title')) urlConfig.header.title = urlParams.get('title');
        if (urlParams.get('avatar')) urlConfig.header.botAvatar = urlParams.get('avatar');

        // Les clés de premier niveau
        const topLevelKeys = ['position', 'mode', 'assetBasePath', 'welcomeMessage'];
        topLevelKeys.forEach(key => {
            if (urlParams.has(key)) urlConfig[key] = urlParams.get(key);
        });

        // Fusion finale
        finalConfig = deepMerge(finalConfig, urlConfig);

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
                handleUserMessage(messageText);
            }
        });
    }

    init();
});
