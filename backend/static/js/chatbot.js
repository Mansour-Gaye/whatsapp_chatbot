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
