// Copilot : conversation libre, puis collecte des infos, puis reprise du chat

// Configuration
const API_ENDPOINT = '/api/chat';
const LEAD_ENDPOINT = '/api/lead';
const TYPING_DELAY = 1000;

// Éléments DOM
const chatbox = document.getElementById('chatbox');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const startBtn = document.getElementById('startBtn');

// État du chat
let isTyping = false;
  let step = 0; // 0: chat libre, 1: collecte infos, 2: chat normal après collecte
  let exchangeCount = 0;
  let history = [];
  let lead = { name: "", email: "", phone: "" };
let missingFields = [];

function isDefaultValue(value) {
  return value === "1234567890" || value.endsWith("@example.com");
}

// Fonctions utilitaires
function getCurrentTime() {
  return new Date().toLocaleTimeString('fr-FR', { 
    hour: '2-digit', 
    minute: '2-digit' 
  });
}

function createMessageElement(content, isUser = false) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
  
  const messageContent = document.createElement('div');
  messageContent.className = 'message-content';
  
  // Convertir les sauts de ligne en <br> et préserver le HTML
  const formattedContent = content
    .replace(/\n/g, '<br>')
    .replace(/\•/g, '•')  // Préserver les puces
    .replace(/\→/g, '→'); // Préserver les flèches
  
  messageContent.innerHTML = formattedContent;
  
  const messageTime = document.createElement('div');
  messageTime.className = 'message-time';
  messageTime.textContent = getCurrentTime();
  
  messageDiv.appendChild(messageContent);
  messageDiv.appendChild(messageTime);
  
  return messageDiv;
}

function showTypingIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;
  chatbox.appendChild(indicator);
    chatbox.scrollTop = chatbox.scrollHeight;
  return indicator;
}

function removeTypingIndicator(indicator) {
  if (indicator && indicator.parentNode) {
    indicator.parentNode.removeChild(indicator);
  }
}

function validateEmail(email) {
  return email.includes('@') && email.includes('.');
}

function validatePhone(phone) {
  return phone.length >= 8;
}

function validateName(name) {
  return name.trim().length >= 2;
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

// Gestion des messages
async function sendMessage() {
  const message = userInput.value.trim();
  if (!message || isTyping) return;
  
  // Ajouter le message de l'utilisateur
  const userMessage = createMessageElement(message, true);
  chatbox.appendChild(userMessage);
  chatbox.scrollTop = chatbox.scrollHeight;
  
  // Vider l'input
  userInput.value = '';
  userInput.style.height = 'auto';
  
  // Désactiver l'input pendant le traitement
  isTyping = true;
  sendBtn.disabled = true;
  userInput.disabled = true;
  
  // Afficher l'indicateur de saisie
  const typingIndicator = showTypingIndicator();
  
  try {
    let response;
    let data;

    if (step === 0) {
      // Chat libre
      exchangeCount++;
      response = await fetch(API_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          history: [...history, { role: 'user', content: message }]
        }),
      });
      
      if (!response.ok) throw new Error('Erreur réseau');
      
      data = await response.json();
      history.push({ role: 'user', content: message });
      history.push({ role: 'assistant', content: data.response });
      
      // Simuler un délai de réponse
      await new Promise(resolve => setTimeout(resolve, TYPING_DELAY));
      
      // Supprimer l'indicateur de saisie
      removeTypingIndicator(typingIndicator);
      
      // Ajouter la réponse du bot
      if (data && data.response) {
        const botMessage = createMessageElement(data.response);
        chatbox.appendChild(botMessage);
        chatbox.scrollTop = chatbox.scrollHeight;
      }
      
      // Après 2 échanges, demander les infos
          if (exchangeCount >= 2) {
        // Attendre un peu avant de demander les infos
        await new Promise(resolve => setTimeout(resolve, 1000));
        const leadRequest = createMessageElement(
          'Au fait, pour mieux vous aider, puis-je connaître votre nom, email et téléphone ?'
        );
        chatbox.appendChild(leadRequest);
        chatbox.scrollTop = chatbox.scrollHeight;
            step = 1;
          }
    } else if (step === 1) {
      // Collecte des infos
      response = await fetch(LEAD_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          input: message,
          lead: lead // Envoyer l'état actuel du lead
        }),
      });
      
      if (!response.ok) throw new Error('Erreur réseau');
      
      data = await response.json();
      
      // Mettre à jour les informations du lead
      if (data.lead) {
        // Ne pas mettre à jour les champs avec des valeurs par défaut
        if (data.lead.name && !isDefaultValue(data.lead.name)) lead.name = data.lead.name;
        if (data.lead.email && !isDefaultValue(data.lead.email)) lead.email = data.lead.email;
        if (data.lead.phone && !isDefaultValue(data.lead.phone)) lead.phone = data.lead.phone;
      }
      
      // Vérifier les champs manquants
      if (checkMissingFields()) {
        // Simuler un délai de réponse
        await new Promise(resolve => setTimeout(resolve, TYPING_DELAY));
        
        // Supprimer l'indicateur de saisie
        removeTypingIndicator(typingIndicator);
        
        const missingFieldsMessage = createMessageElement(getMissingFieldsMessage());
        chatbox.appendChild(missingFieldsMessage);
        chatbox.scrollTop = chatbox.scrollHeight;
      } else {
        // Toutes les informations sont présentes
        response = await fetch(LEAD_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            input: message,
            lead: lead,
            save: true 
          }),
        });
        
        if (!response.ok) throw new Error('Erreur réseau');
        
        // Simuler un délai de réponse
        await new Promise(resolve => setTimeout(resolve, TYPING_DELAY));
        
        // Supprimer l'indicateur de saisie
        removeTypingIndicator(typingIndicator);
        
        const confirmation = createMessageElement(
          'Merci, vos informations ont bien été enregistrées !'
        );
        chatbox.appendChild(confirmation);
        chatbox.scrollTop = chatbox.scrollHeight;
        step = 2;
      }
    } else {
      // Chat normal après collecte
      response = await fetch(API_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          history: [...history, { role: 'user', content: message }]
        }),
      });
      
      if (!response.ok) throw new Error('Erreur réseau');
      
      data = await response.json();
      history.push({ role: 'user', content: message });
      history.push({ role: 'assistant', content: data.response });
      
      // Simuler un délai de réponse
      await new Promise(resolve => setTimeout(resolve, TYPING_DELAY));
      
      // Supprimer l'indicateur de saisie
      removeTypingIndicator(typingIndicator);
      
      // Ajouter la réponse du bot
      if (data && data.response) {
        const botMessage = createMessageElement(data.response);
        chatbox.appendChild(botMessage);
        chatbox.scrollTop = chatbox.scrollHeight;
      }
    }
    
  } catch (error) {
    console.error('Erreur:', error);
    removeTypingIndicator(typingIndicator);
    
    // Afficher un message d'erreur
    const errorMessage = createMessageElement(
      'Désolé, une erreur est survenue. Veuillez réessayer.'
    );
    chatbox.appendChild(errorMessage);
  } finally {
    // Réactiver l'input
    isTyping = false;
    sendBtn.disabled = false;
    userInput.disabled = false;
    userInput.focus();
  }
}

// Gestion des événements
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

startBtn.addEventListener('click', () => {
  // Réinitialiser le chat
  chatbox.innerHTML = '';
  userInput.value = '';
  userInput.style.height = 'auto';
  step = 0;
  exchangeCount = 0;
  history = [];
  
  // Ajouter un message de bienvenue
  const welcomeMessage = createMessageElement(
    'Bonjour ! Je suis l\'assistant virtuel de TRANSLAB INTERNATIONAL, spécialisé en Interprétation de conférence et Traduction. Comment puis-je vous aider aujourd\'hui ? 🌍'
  );
  chatbox.appendChild(welcomeMessage);
});

// Initialisation
window.addEventListener('load', () => {
  startBtn.click();
});

COMPANY_NAME = "TRANSLAB INTERNATIONAL"
COMPANY_SPECIALTY = "Interpretation de conference et Traduction"

// chatbot.js - Logique du chatbot web

let messageHistory = [];

// Ajoute un message dans la zone de chat
function appendMessage(content, role = "user") {
    const chatMessages = document.getElementById("chatMessages");
    const msgDiv = document.createElement("div");
    msgDiv.className = role === "user" ? "chat-message user" : "chat-message bot";
    msgDiv.textContent = content;
    chatMessages.appendChild(msgDiv);
    // Auto-scroll vers le bas
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Envoie le message utilisateur au backend et affiche la réponse
async function sendMessage(userInput) {
    messageHistory.push({ role: "user", content: userInput });
    appendMessage(userInput, "user");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ history: messageHistory })
        });
        if (!response.ok) throw new Error("Network response was not ok");
        const data = await response.json();
        if (data && data.response) {
            messageHistory.push({ role: "assistant", content: data.response });
            appendMessage(data.response, "bot");
        } else {
            appendMessage("Réponse invalide du serveur.", "bot");
        }
    } catch (error) {
        appendMessage("Erreur de connexion.", "bot");
    }
}

// Initialise les listeners et le chat
function initChat() {
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");

    chatForm.addEventListener("submit", function(e) {
        e.preventDefault();
        const userInput = chatInput.value.trim();
        if (userInput) {
            sendMessage(userInput);
            chatInput.value = "";
            chatInput.focus();
        }
    });
}

window.addEventListener("DOMContentLoaded", initChat);
