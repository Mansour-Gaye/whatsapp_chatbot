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
    const quickRepliesContainerStatic = document.getElementById('quick-replies-container-static');
    const chatboxForm = document.getElementById('chatbox-form');
    const chatboxInput = document.getElementById('chatbox-input');
    const closeChatboxBtn = document.getElementById('close-chatbox');
    const chatLauncher = document.getElementById('chat-launcher');
    const chatLauncherBubble = document.getElementById('chat-launcher-bubble');
    const progressBar = document.querySelector('.progress-bar');


    let chatHistory = [];
    let config = {};
    let progressTimeout = null;
    let inactivityTimer = null;
    let visitorId = null; // Variable pour stocker l'ID du visiteur
    let hasUserInteracted = false; // Pour suivre l'interaction de l'utilisateur

    let leadStep = 0; // 0: chat libre, 1: collecte, 2: chat normal après collecte
    let leadExchangeCount = 0;
    window.leadData = { name: "", email: "", phone: "" };
    let leadMissingFields = [];


    // =================================================================================
    //  FONCTION DE GESTION DU VISITEUR
    // =================================================================================

    function getOrSetVisitorId() {
        let id = localStorage.getItem('chatbox-visitor-id');
        if (!id) {
            // Génère un ID simple mais suffisamment unique pour ce cas d'usage
            id = `visitor_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
            localStorage.setItem('chatbox-visitor-id', id);
        }
        return id;
    }

    async function loadInitialData() {
        if (!visitorId) return;

        try {
            const response = await fetch('/api/visitor/lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visitorId })
            });

            if (!response.ok) {
                console.error("Erreur lors de la récupération des données du visiteur.");
                return;
            }

            const data = await response.json();

            if (data.status === 'success') {
                // Gérer les informations du lead
                if (data.lead) {
                    console.log("Lead trouvé pour ce visiteur:", data.lead);
                    window.leadData = {
                        name: data.lead.name || "",
                        email: data.lead.email || "",
                        phone: data.lead.phone || ""
                    };
                    // Si les informations sont complètes, on saute l'étape de collecte
                    if (window.leadData.name && window.leadData.email && window.leadData.phone) {
                        leadStep = 2; // Passe en mode chat normal
                        console.log("Informations du lead complètes. Passage à l'étape 2.");
                    }
                }

                // Gérer l'historique de conversation
                if (data.history && data.history.length > 0) {
                    console.log(`Historique de conversation trouvé (${data.history.length} messages). Remplacement de l'historique local.`);
                    // Remplacer l'historique local par celui du serveur
                    chatHistory = data.history.map(msg => ({
                        text: msg.text,
                        sender: msg.sender === 'assistant' ? 'bot' : 'user', // Assurer la compatibilité du nom
                        timestamp: new Date(msg.timestamp).getTime()
                    }));

                    // Vider l'affichage et re-rendre les messages
                    chatboxMessages.innerHTML = '';
                    chatHistory.forEach(messageData => renderMessage({ ...messageData, isHistory: true }));
                    saveHistory(); // Sauvegarder l'historique du serveur dans le localStorage
                    return true; // Indiquer que l'historique a été chargé depuis le serveur
                }
            }
        } catch (error) {
            console.error("Erreur dans loadInitialData:", error);
        }
        return false; // Indiquer qu'aucun historique n'a été chargé depuis le serveur
    }


    // =================================================================================
    //  FONCTIONS DE RENDU (Construction de l'interface)
    // =================================================================================


    function renderQuickReplies(replies) {
        // Vider l'ancien contenu
        quickRepliesContainerStatic.innerHTML = '';

        if (!replies || replies.length === 0) {
            quickRepliesContainerStatic.style.display = 'none';
            return;
        }

        const container = document.createElement('div');
        container.className = 'quick-replies-container';

        replies.forEach(replyText => {
            const button = document.createElement('button');
            button.className = 'quick-reply-btn';
            button.textContent = replyText;
            button.addEventListener('click', () => handleQuickReplyClick(replyText));
            container.appendChild(button);
        });

        quickRepliesContainerStatic.appendChild(container);
        quickRepliesContainerStatic.style.display = 'block';
        chatboxMessages.scrollTop = chatboxMessages.scrollHeight; // S'assurer que tout est visible
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

    function createImageGrid(imageUrls) {
        const gridContainer = document.createElement('div');
        gridContainer.className = 'image-grid-container';

        imageUrls.forEach(url => {
            const img = document.createElement('img');
            img.src = url;
            img.alt = 'Image de la grille';
            img.loading = 'lazy';
            img.className = 'image-grid-item';
            gridContainer.appendChild(img);
        });

        return gridContainer;
    }


    function renderMessage(messageData) {
        let { text, sender, timestamp, options = {}, isHistory } = messageData;

        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) typingIndicator.remove();

        const messageBubble = document.createElement('div');
        messageBubble.classList.add('message-bubble', sender);

        // --- Logique de Rendu de l'En-tête d'Émotion ---
        if (sender === 'bot' && options.emotion_image) {
            const emotionHeader = document.createElement('div');
            emotionHeader.className = 'emotion-header';
            const img = document.createElement('img');
            img.src = options.emotion_image;
            img.alt = "Illustration d'émotion";
            img.loading = 'lazy';
            emotionHeader.appendChild(img);
            messageBubble.appendChild(emotionHeader);
        }
        // --- Fin de la Logique de Rendu de l'En-tête d'Émotion ---

        // --- Emotion Parsing Logic ---
        const emotionRegex = /\[emotion:\s*([^\]]+)\]/g;
        const emotionMatches = text.match(emotionRegex);
        
        if (emotionMatches && sender === 'bot') {
            emotionMatches.forEach(tag => {
                const emotionName = tag.replace(emotionRegex, '$1').trim();
                const emotionBadge = document.createElement('div');
                emotionBadge.className = 'emotion-badge';
                emotionBadge.textContent = `💭 ${emotionName}`;
                messageBubble.appendChild(emotionBadge);
            });
            text = text.replace(emotionRegex, '').trim();
        }

        // --- Image Parsing Logic ---
        const imageRegex = /\[image:\s*([^]]+)\]/g;
        const imageMatches = text.match(imageRegex);

        if (imageMatches) {
            imageMatches.forEach(tag => {
                const imageName = tag.replace(imageRegex, '$1').trim();
                const img = document.createElement('img');
                // Le chemin doit être relatif à la racine du serveur web, qui sert le dossier 'static'
                img.src = `/static/public/${imageName}`;
                img.alt = imageName;
                img.style.maxWidth = '100%';
                img.style.borderRadius = '12px';
                img.style.marginTop = '8px';
                messageBubble.appendChild(img);
            });
            text = text.replace(imageRegex, '').trim();
        }
        // --- End Image Parsing Logic ---

        if (text) {
            const messageContent = document.createElement('div');
            messageContent.classList.add('message-content');
            if (sender === 'bot') {
                messageContent.innerHTML = DOMPurify.sanitize(marked.parse(text));
            } else {
                messageContent.textContent = text;
            }
            messageBubble.appendChild(messageContent);
        }

        // --- Logique de Rendu de la Grille d'Images ---
        if (options.carousel_images && Array.isArray(options.carousel_images) && options.carousel_images.length > 0) {
            const gridElement = createImageGrid(options.carousel_images);
            // Insérer la grille après le contenu textuel s'il existe, ou en premier.
            if (messageBubble.querySelector('.message-content')) {
                messageBubble.querySelector('.message-content').insertAdjacentElement('afterend', gridElement);
            } else {
                messageBubble.prepend(gridElement);
            }
        }
        // --- Fin de la Logique de Rendu de la Grille ---

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

        // La gestion des quick replies est maintenant externe à cette fonction
        // pour éviter qu'ils soient ajoutés au milieu de l'historique.
    }

    // =================================================================================
    //  FONCTIONS DE LOGIQUE (Gestion des actions)
    // =================================================================================


    function addMessage(text, sender, options = {}) {
        const messageData = { text, sender, timestamp: Date.now(), options };
        chatHistory.push(messageData);
        saveHistory();
        renderMessage(messageData);

        // Gérer les quick replies seulement pour les messages du bot
        if (sender === 'bot' && options.quickReplies) {
            renderQuickReplies(options.quickReplies);
        } else if (sender === 'user') {
            renderQuickReplies([]); // Vider les quick replies quand l'utilisateur envoie un message
            hasUserInteracted = true; // L'utilisateur a interagi
        }

        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;

        // --- Inactivity Timer ---
        clearTimeout(inactivityTimer);
        // Only set a new timer if the message is from the bot, it's not an inactivity prompt, AND the user has interacted at least once.
        if (hasUserInteracted && sender === 'bot' && !options.isInactivityPrompt) {
            inactivityTimer = setTimeout(() => {
                addMessage("Puis-je vous aider avec autre chose ?", 'bot', { isInactivityPrompt: true, quickReplies: ['Oui', 'Non'] });
            }, 60000); // 60 seconds
        }
    }

    function displayLeadSummary(lead) {
        let summaryText = "Merci ! Veuillez vérifier les informations que vous avez fournies :\n\n";
        summaryText += `Nom : ${lead.name || 'Non fourni'}\n`;
        summaryText += `Email : ${lead.email || 'Non fourni'}\n`;
        summaryText += `Téléphone : ${lead.phone || 'Non fourni'}`;

        addMessage(summaryText, 'bot', {
            quickReplies: ["C'est correct", "Modifier les informations"]
        });
    }


    async function sendToBackend() {
        const historyPayload = chatHistory.map(msg => ({
            role: msg.sender === 'user' ? 'user' : 'assistant',
            content: msg.text
        }));

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history: historyPayload, visitorId: visitorId })
            });

            // La réponse du backend est maintenant toujours un objet JSON, même en cas d'erreur
            const data = await response.json();

            if (!response.ok) {
                console.error("Backend error:", data.response || `HTTP error! status: ${response.status}`);
                // Retourner un objet d'erreur standardisé
                return { status: "error", response: data.response || "Une erreur technique est survenue." };
            }

            return data; // Contient { status, response, options }
        } catch (e) {
            console.error("Network or fetch error:", e);
            // Retourner un objet d'erreur standardisé
            return { status: "error", response: "Erreur de connexion au serveur." };
        }
    }

    function handleQuickReplyClick(text) {
        // Log the click event to the backend in a "fire and forget" way
        if (visitorId) {
            fetch('/api/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    visitorId: visitorId,
                    event_type: 'quick_reply_click',
                    event_value: text
                })
            }).catch(error => console.error('Error tracking event:', error)); // Log error but don't block user flow
        }

        addMessage(text, 'user'); // addMessage will now hide the quick replies
        chatboxInput.value = '';
        handleUserMessage(text); // Real call to the backend
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
    localStorage.setItem('chatbox-state', String(isOpen));

    // Gérer la bulle de notification
    if (isOpen) {
        chatLauncherBubble.classList.remove('visible');
    } else {
        // Afficher la bulle après un court délai lorsque le chatbot est fermé
        setTimeout(() => {
            // S'assurer que le chatbot n'a pas été rouvert pendant le délai
            if (!chatboxContainer.classList.contains('open')) {
                chatLauncherBubble.classList.add('visible');
            }
        }, 1000); // Délai de 1 seconde
    }

    if (isOpen) {
        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;
    }
}

    // =================================================================================
    //  PERSISTANCE & CONFIGURATION
    // =================================================================================

    function deepMerge(target, source) {
        const output = { ...target };
        if (isObject(target) && isObject(source)) {
            Object.keys(source).forEach(key => {
                if (isObject(source[key])) {
                    if (!(key in target))
                        Object.assign(output, { [key]: source[key] });
                    else
                        output[key] = deepMerge(target[key], source[key]);
                } else {
                    Object.assign(output, { [key]: source[key] });
                }
            });
        }
        return output;
    }

    function isObject(item) {
        return (item && typeof item === 'object' && !Array.isArray(item));
    }

    function loadConfig() {
        // 1. Start with default config
        let mergedConfig = { ...defaultConfig };

        // 2. Merge with window config object if it exists
        if (window.chatboxConfig && isObject(window.chatboxConfig)) {
            mergedConfig = deepMerge(mergedConfig, window.chatboxConfig);
        }

        // 3. Override with URL parameters for quick customization
        const urlParams = new URLSearchParams(window.location.search);
        const paramsConfig = {
            position: urlParams.get('position'),
            theme: { primary: urlParams.get('primaryColor') ? `#${urlParams.get('primaryColor')}` : null },
            header: {
                title: urlParams.get('title'),
                botAvatar: urlParams.get('avatar')
            },
            assetBasePath: urlParams.get('basePath')
        };

        // Clean up null/undefined values from paramsConfig before merging
        Object.keys(paramsConfig).forEach(key => {
            if (paramsConfig[key] === null || paramsConfig[key] === undefined) {
                delete paramsConfig[key];
            }
            if (isObject(paramsConfig[key])) {
                 Object.keys(paramsConfig[key]).forEach(subKey => {
                    if (paramsConfig[key][subKey] === null || paramsConfig[key][subKey] === undefined) {
                        delete paramsConfig[key][subKey];
                    }
                 });
                 if (Object.keys(paramsConfig[key]).length === 0) {
                     delete paramsConfig[key];
                 }
            }
        });

        mergedConfig = deepMerge(mergedConfig, paramsConfig);
        return mergedConfig;
    }

    function applyConfig(config) {
        // Apply theme colors
        document.documentElement.style.setProperty('--primary-color', config.theme.primary);
        document.documentElement.style.setProperty('--user-message-bg', config.theme.userMessageBg || config.theme.primary);

        // Apply position
        chatboxContainer.classList.add(config.position || 'bottom-right');
        chatLauncher.classList.add(config.position || 'bottom-right');

        // Apply header
        const headerTitle = document.querySelector('.chatbox-header-title');
        if (headerTitle) headerTitle.textContent = config.header.title;

        const botAvatarImg = document.getElementById('bot-avatar');
        if (botAvatarImg) {
            let avatarUrl = config.header.botAvatar;
            // Handle base path for avatar
            if (config.assetBasePath && !avatarUrl.startsWith('http') && !avatarUrl.startsWith('/')) {
                avatarUrl = `${config.assetBasePath}${avatarUrl}`;
            }
            botAvatarImg.src = avatarUrl;
        }
    }

    function saveHistory() {
        try {
            const limitedHistory = chatHistory.slice(-50);
            localStorage.setItem('chatbox-history', JSON.stringify(limitedHistory));
        } catch (e) {
            console.error("Erreur de sauvegarde:", e);
        }
    }


    function loadHistoryFromLocal() {
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

        // --- Progress Bar Start ---
        clearTimeout(progressTimeout);
        progressTimeout = setTimeout(() => progressBar.classList.add('visible'), 500);
        // --- Progress Bar End ---

        try {
            if (leadStep === 1) {
                const refusal_keywords = ['non', 'no', 'pas maintenant', 'non merci', 'je ne veux pas'];
                const isRefusal = refusal_keywords.some(keyword => userMessage.toLowerCase().includes(keyword));

                if (isRefusal) {
                    addMessage("Pas de problème ! Continuons.", 'bot');
                    leadStep = 2; // Passer à l'étape de chat normal
                    // Pas besoin de 'return' ici, le 'else' suivant gère le flux
                } else {
                    const response = await fetch('/api/lead', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            input: userMessage,
                            current_lead: window.leadData,
                            visitorId: visitorId // Inclure le visitorId
                        })
                    });
                    const data = await response.json();
                    if (data.status === "success") {
                        window.leadData = data.lead;

                        if (data.complete && leadStep === 1) { // Only show summary once on completion
                            displayLeadSummary(data.lead);
                        } else {
                            addMessage(data.message || "Merci pour ces informations !", 'bot');
                        }

                        leadStep = 2; // Toujours passer à l'étape 2 pour ne pas redemander en boucle
                    } else {
                        throw new Error(data.message || "Erreur serveur");
                    }
                }
            } else { // Handles leadStep 0 and 2
                const botResponse = await sendToBackend(); // C'est maintenant un objet

                if (botResponse.status === 'success') {
                    // Passer le texte et les options (qui peuvent inclure le carrousel) à addMessage
                    addMessage(botResponse.response, 'bot', botResponse.options || {});
                } else {
                    // En cas d'erreur retournée par le backend
                    addMessage(botResponse.response, 'bot');
                }

                if (leadStep === 0) {
                    leadExchangeCount++;
                    if (leadExchangeCount >= 2) {
                        setTimeout(() => {
                            addMessage("Au fait, pour mieux vous aider, puis-je connaître votre nom, email et téléphone ?", 'bot');
                            leadStep = 1;
                        }, 1000);
                    }
                }
            }
        } catch (e) {
            addMessage(`Désolé, une erreur est survenue : ${e.message}`, 'bot');
        } finally {
            toggleTypingIndicator(false);
            chatboxInput.disabled = false;
            chatboxInput.focus();
            // --- Progress Bar Cleanup ---
            clearTimeout(progressTimeout);
            progressBar.classList.remove('visible');
            // --- Progress Bar Cleanup ---
        }
    }

    function applySystemTheme() {
        // We don't force a theme if one is already set via config (e.g. url params)
        // This function just sets the default based on OS.
        const storedTheme = localStorage.getItem('chatbox-theme');
        if (storedTheme) {
            document.documentElement.setAttribute('data-theme', storedTheme);
            return;
        }

        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');

        function setTheme(isDark) {
            const theme = isDark ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('chatbox-theme', theme);
        }

        setTheme(prefersDark.matches);

        prefersDark.addEventListener('change', (e) => {
            setTheme(e.matches);
        });
    }

    // Initialisation UI et listeners déplacée dans init()
    async function init() {
        visitorId = getOrSetVisitorId(); // Récupérer ou créer l'ID du visiteur
        console.log(`Visitor ID: ${visitorId}`); // Pour le débogage

        config = loadConfig();
        applyConfig(config);
        applySystemTheme();

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

        // Gestion des événements
        chatLauncher.addEventListener('click', () => toggleChatbox(true));
        closeChatboxBtn.addEventListener('click', () => toggleChatbox(false));

        // Afficher la bulle de notification au démarrage si le chatbot est fermé
        if (!initialState) {
            setTimeout(() => {
                chatLauncherBubble.classList.add('visible');
            }, 2000); // Délai initial plus long
        }

        // Charger l'historique (serveur ou local) et afficher le message de bienvenue si nécessaire
        const historyLoadedFromServer = await loadInitialData();

        if (!historyLoadedFromServer) {
            const historyLoadedFromLocal = loadHistoryFromLocal();
            if (!historyLoadedFromLocal) {
                addMessage(config.welcomeMessage, 'bot', {
                    quickReplies: config.initialQuickReplies
                });
            }
        }

        chatboxMessages.scrollTop = chatboxMessages.scrollHeight;

        chatboxForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const messageText = chatboxInput.value.trim();
            if (messageText) {
                addMessage(messageText, 'user'); // addMessage va maintenant cacher les quick replies
                chatboxInput.value = '';
                handleUserMessage(messageText);
            }
        });
    }

    // Appel final
    init();
});