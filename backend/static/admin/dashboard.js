document.addEventListener('DOMContentLoaded', () => {
    const leadsTbody = document.getElementById('leads-tbody');
    const nameFilter = document.getElementById('name-filter');
    const emailFilter = document.getElementById('email-filter');
    const dateFilter = document.getElementById('date-filter');
    const modal = document.getElementById('conversation-modal');
    const modalTitle = document.getElementById('modal-title');
    const conversationHistory = document.getElementById('conversation-history');
    const closeButton = document.querySelector('.close-button');

    let allLeads = [];

    // --- Fonctions ---

    /**
     * Affiche les leads dans le tableau
     * @param {Array} leads - Le tableau de leads à afficher
     */
    const renderLeads = (leads) => {
        leadsTbody.innerHTML = '';
        if (leads.length === 0) {
            leadsTbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Aucun lead trouvé.</td></tr>';
            return;
        }

        leads.forEach(lead => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${lead.name || 'N/A'}</td>
                <td>${lead.email || 'N/A'}</td>
                <td>${lead.phone || 'N/A'}</td>
                <td>${new Date(lead.created_at).toLocaleString('fr-FR')}</td>
                <td>
                    <button class="action-button" data-visitor-id="${lead.visitor_id}" data-lead-name="${lead.name || 'Inconnu'}">
                        Voir l'historique
                    </button>
                </td>
            `;
            leadsTbody.appendChild(tr);
        });
    };

    /**
     * Filtre les leads en fonction des valeurs des champs de filtre
     */
    const filterLeads = () => {
        const nameQuery = nameFilter.value.toLowerCase();
        const emailQuery = emailFilter.value.toLowerCase();
        const dateQuery = dateFilter.value;

        const filteredLeads = allLeads.filter(lead => {
            const leadDate = new Date(lead.created_at).toISOString().split('T')[0];
            const nameMatch = !nameQuery || (lead.name && lead.name.toLowerCase().includes(nameQuery));
            const emailMatch = !emailQuery || (lead.email && lead.email.toLowerCase().includes(emailQuery));
            const dateMatch = !dateQuery || leadDate === dateQuery;
            return nameMatch && emailMatch && dateMatch;
        });

        renderLeads(filteredLeads);
    };

    /**
     * Affiche le modal de l'historique de conversation
     * @param {string} visitorId - L'ID du visiteur
     * @param {string} leadName - Le nom du lead
     */
    const showConversationModal = async (visitorId, leadName) => {
        modalTitle.textContent = `Historique de la Conversation - ${leadName}`;
        conversationHistory.innerHTML = '<p>Chargement...</p>';
        modal.style.display = 'block';

        try {
            const response = await fetch(`/api/admin/leads/${visitorId}/conversations`);
            if (!response.ok) throw new Error('Erreur réseau');
            const conversations = await response.json();

            conversationHistory.innerHTML = '';
            if (conversations.length === 0) {
                conversationHistory.innerHTML = '<p>Aucun historique de conversation trouvé.</p>';
                return;
            }

            conversations.forEach(msg => {
                const messageDiv = document.createElement('div');
                messageDiv.classList.add('conversation-message', msg.role);
                const formattedDate = new Date(msg.created_at).toLocaleString('fr-FR');
                messageDiv.innerHTML = `
                    <strong>${msg.role} (${formattedDate})</strong>
                    <p>${msg.content}</p>
                `;
                conversationHistory.appendChild(messageDiv);
            });

        } catch (error) {
            conversationHistory.innerHTML = `<p>Erreur lors du chargement de l'historique : ${error.message}</p>`;
            console.error(error);
        }
    };

    // --- Écouteurs d'événements ---

    // Chargement initial des leads
    fetch('/api/admin/leads')
        .then(response => {
            if (response.status === 401) { // Non autorisé
                window.location.href = '/admin/login';
                return;
            }
            return response.json();
        })
        .then(data => {
            allLeads = data;
            renderLeads(allLeads);
        })
        .catch(error => {
            console.error('Erreur lors du chargement des leads:', error);
            leadsTbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Erreur de chargement des données.</td></tr>';
        });

    // Écouteurs pour les filtres
    nameFilter.addEventListener('input', filterLeads);
    emailFilter.addEventListener('input', filterLeads);
    dateFilter.addEventListener('change', filterLeads);

    // Écouteur pour les boutons "Voir l'historique" (délégation d'événement)
    leadsTbody.addEventListener('click', (event) => {
        if (event.target.classList.contains('action-button')) {
            const visitorId = event.target.dataset.visitorId;
            const leadName = event.target.dataset.leadName;
            if (visitorId) {
                showConversationModal(visitorId, leadName);
            }
        }
    });

    // Fermeture du modal
    closeButton.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
});
