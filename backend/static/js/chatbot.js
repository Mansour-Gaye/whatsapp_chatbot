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
            botAvatar: '/static/img/cultural-nuance.png'
        },
        welcomeMessage: 'Bonjour ! Comment puis-je vous aider aujourd\'hui ?',
        initialQuickReplies: ['Info produit', 'Support technique', 'Autre question']
        };
    
    // L'appel à init() sera déplacé à la fin du fichier

    // ---------------------------
    const chatboxContainer = document.getElementById('chatbox-container');
    const chatboxMessages = document.getElementById('chatbox-messages');
    const chatboxForm = document.getElementById('chatbox-form');
    const chatboxInput = document.getElementById('chatbox-input');
    const closeChatboxBtn = document.getElementById('close-chatbox');
    const chatLauncher = document.getElementById('chat-launcher');


    let chatHistory = [];
    let config = {};

    let leadStep = 0; // 0: chat libre, 1: collecte, 2: chat normal après collecte
    let leadExchangeCount = 0;
window.leadData = { name: "", email: "", phone: "" };
    let leadMissingFields = [];


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


    async function sendToBackend(history) {
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history })
            });
            const data = await response.json();
            if (data.status === "success") {
                return data.response;
            } else {
                return "Je rencontre un souci technique. Merci de réessayer plus tard.";
            }
        } catch (e) {
            return "Erreur de connexion au serveur.";
        }
    }

    // SUPPRIME la première définition de handleUserMessage (gardera la version simplifiée plus bas)


    function handleQuickReplyClick(text) {
        const qrContainers = document.querySelectorAll('.quick-replies-container');
        qrContainers.forEach(container => container.remove());
        addMessage(text, 'user');
        chatboxInput.value = '';
        handleUserMessage(text); // Appel réel au backend
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


function toggleChatbox(forceState) {
    const isOpen = typeof forceState === 'boolean' 
        ? forceState 
        : !chatboxContainer.classList.contains('open');
    chatboxContainer.classList.toggle('open', isOpen);
    chatLauncher.classList.toggle('hidden', isOpen);
    localStorage.setItem('chatbox-state', isOpen);
    // Forcer le recalcul du layout
    chatboxMessages.scrollTop = chatboxMessages.scrollHeight;
}

    // =================================================================================
    //  PERSISTANCE & CONFIGURATION
    // =================================================================================


    function saveHistory() {
        try {
            const limitedHistory = chatHistory.slice(-50);
            localStorage.setItem('chatbox-history', JSON.stringify(limitedHistory));
        } catch (e) {
            console.error("Erreur de sauvegarde:", e);
        }
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


    async function handleUserMessage(userMessage) {
        if (userMessage.toLowerCase().includes('reset')) {
            localStorage.clear();
            location.reload();
            return;
        }
        toggleTypingIndicator(true);
        chatboxInput.disabled = true;

        if (leadStep === 1) {
            try {
                const response = await fetch('/api/lead', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        input: userMessage,
                        current_lead: window.leadData
                    })
                });
                const data = await response.json();
                if (data.status === "success") {
                    window.leadData = data.lead;
                    addMessage(data.message || "Merci pour ces informations !", 'bot');
                    leadStep = data.complete ? 2 : 1;
                } else {
                    throw new Error(data.message || "Erreur serveur");
                }
            } catch (e) {
                addMessage(`Désolé, une erreur est survenue : ${e.message}`, 'bot');
            } finally {
                toggleTypingIndicator(false);
                chatboxInput.disabled = false;
                chatboxInput.focus();
            }
            return;
        }

        // Chat normal ou début
        if (leadStep === 0) {
            leadExchangeCount++;
            const history = chatHistory.map(msg => ({
                role: msg.sender === 'user' ? 'user' : 'assistant',
                content: msg.text
            }));
            history.push({ role: 'user', content: userMessage });
            const botReply = await sendToBackend(history);
            toggleTypingIndicator(false);
            addMessage(botReply, 'bot');
            chatboxInput.disabled = false;
            chatboxInput.focus();

            if (leadExchangeCount >= 2) {
                setTimeout(() => {
                    addMessage("Au fait, pour mieux vous aider, puis-je connaître votre nom, email et téléphone ?", 'bot');
                    leadStep = 1;
                }, 1000);
            }
        } else if (leadStep === 2) {
            // Chat normal après collecte
            const history = chatHistory.map(msg => ({
                role: msg.sender === 'user' ? 'user' : 'assistant',
                content: msg.text
            }));
            history.push({ role: 'user', content: userMessage });
            const botReply = await sendToBackend(history);
            toggleTypingIndicator(false);
            addMessage(botReply, 'bot');
            chatboxInput.disabled = false;
            chatboxInput.focus();
        }
    }

    // Initialisation UI et listeners déplacée dans init()
    function init() {
        config = loadConfig();
        applyConfig(config);

        // Initialisation de l'état
        const savedState = localStorage.getItem('chatbox-state');
        const initialState = savedState ? savedState === 'true' : false;
        // Fermer par défaut si pas d'état sauvegardé
        if (!initialState) {
            chatboxContainer.classList.remove('open');
            chatLauncher.classList.remove('hidden');
        } else {
            chatboxContainer.classList.add('open');
            chatLauncher.classList.add('hidden');
        }

        // Vérifier le chargement des messages
        console.log('History loaded:', loadHistory());

        // Gestion des événements
        chatLauncher.addEventListener('click', () => {
            chatboxContainer.classList.add('open');
            chatLauncher.classList.add('hidden');
            localStorage.setItem('chatbox-state', 'true');
        });

        closeChatboxBtn.addEventListener('click', () => {
            chatboxContainer.classList.remove('open');
            chatLauncher.classList.remove('hidden');
            localStorage.setItem('chatbox-state', 'false');
        });

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

    // Appel final
    init();
});
