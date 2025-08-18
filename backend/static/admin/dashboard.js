document.addEventListener('DOMContentLoaded', () => {

    // --- STATE MANAGEMENT ---
    const state = {
        allLeads: [],
        filteredLeads: [],
        sortColumn: 'created_at',
        sortDirection: 'desc',
        currentPage: 1,
        rowsPerPage: 10,
    };

    // --- SELECTORS ---
    const themeToggle = document.getElementById('theme-toggle');
    const darkIcon = document.getElementById('theme-toggle-dark-icon');
    const lightIcon = document.getElementById('theme-toggle-light-icon');
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.section-content');
    const leadsTbody = document.getElementById('leads-tbody');
    const totalLeadsEl = document.getElementById('total-leads');
    const leadsChartCanvas = document.getElementById('leads-chart');
    const searchFilter = document.getElementById('search-filter');
    const paginationControls = document.getElementById('pagination-controls');
    const sortableHeaders = document.querySelectorAll('.sortable');

    // Modals
    const conversationModal = document.getElementById('conversation-modal');
    const editLeadModal = document.getElementById('edit-lead-modal');

    // --- RENDER FUNCTIONS ---

    const render = () => {
        const query = searchFilter.value.toLowerCase();
        state.filteredLeads = state.allLeads.filter(lead =>
            (lead.name && lead.name.toLowerCase().includes(query)) ||
            (lead.email && lead.email.toLowerCase().includes(query)) ||
            (lead.phone && lead.phone.toLowerCase().includes(query))
        );

        state.filteredLeads.sort((a, b) => {
            let valA = a[state.sortColumn] || ''; let valB = b[state.sortColumn] || '';
            if (state.sortColumn === 'created_at') { valA = new Date(valA); valB = new Date(valB); }
            if (valA < valB) return state.sortDirection === 'asc' ? -1 : 1;
            if (valA > valB) return state.sortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        const start = (state.currentPage - 1) * state.rowsPerPage;
        const end = start + state.rowsPerPage;
        const paginatedLeads = state.filteredLeads.slice(start, end);

        renderLeadsTable(paginatedLeads);
        renderPagination();
        updateSortIcons();
    };

    const renderLeadsTable = (leads) => {
        leadsTbody.innerHTML = '';
        if (leads.length === 0) {
            leadsTbody.innerHTML = `<tr><td colspan="5" class="text-center p-4">Aucun lead ne correspond à votre recherche.</td></tr>`;
            return;
        }
        leads.forEach(lead => {
            const tr = document.createElement('tr');
            tr.className = 'border-b dark:border-gray-700';
            const historyDisabled = !lead.visitor_id ? 'disabled opacity-50 cursor-not-allowed' : '';
            const editDisabled = !lead.visitor_id ? 'disabled opacity-50 cursor-not-allowed' : '';

            tr.innerHTML = `
                <td class="p-4">${lead.name || 'N/A'}</td>
                <td class="p-4">${lead.email || 'N/A'}</td>
                <td class="p-4">${lead.phone || 'N/A'}</td>
                <td class="p-4">${new Date(lead.created_at).toLocaleString('fr-FR')}</td>
                <td class="p-4 space-x-2">
                    <button class="history-button text-blue-500 hover:underline ${historyDisabled}" data-visitor-id="${lead.visitor_id}" data-lead-name="${lead.name || 'Inconnu'}" ${historyDisabled}>
                        Historique
                    </button>
                    <button class="edit-button text-green-500 hover:underline ${editDisabled}" data-visitor-id="${lead.visitor_id}" ${editDisabled}>
                        Modifier
                    </button>
                </td>
            `;
            leadsTbody.appendChild(tr);
        });
    };

    const renderPagination = () => {
        const totalPages = Math.ceil(state.filteredLeads.length / state.rowsPerPage);
        paginationControls.innerHTML = '';
        if (totalPages <= 1) return;
        let buttons = '';
        for (let i = 1; i <= totalPages; i++) {
            const activeClass = i === state.currentPage ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700';
            buttons += `<button class="px-3 py-1 rounded ${activeClass}" data-page="${i}">${i}</button>`;
        }
        paginationControls.innerHTML = `<div class="flex space-x-2">${buttons}</div><div class="text-sm text-gray-500">Page ${state.currentPage} sur ${totalPages}</div>`;
    };

    const updateSortIcons = () => {
        sortableHeaders.forEach(header => {
            const icon = header.querySelector('.sort-icon');
            icon.textContent = header.dataset.sort === state.sortColumn ? (state.sortDirection === 'asc' ? ' ▲' : ' ▼') : '';
        });
    };

    const renderLeadsChart = (leadsOverTime) => {
        new Chart(leadsChartCanvas, {
            type: 'bar', data: { labels: leadsOverTime.labels, datasets: [{
                label: 'Leads par jour', data: leadsOverTime.data,
                backgroundColor: 'rgba(52, 152, 219, 0.5)', borderColor: 'rgba(52, 152, 219, 1)', borderWidth: 1
            }]}, options: { scales: { y: { beginAtZero: true } } }
        });
    };

    // --- MODAL & FORM HANDLERS ---

    const openModal = (modal) => { modal.classList.remove('hidden'); modal.classList.add('flex'); };
    const closeModal = (modal) => { modal.classList.add('hidden'); modal.classList.remove('flex'); };

    const handleHistoryClick = async (visitorId, leadName) => {
        const title = conversationModal.querySelector('#modal-title');
        const historyDiv = conversationModal.querySelector('#conversation-history');
        title.textContent = `Historique de Conversation - ${leadName}`;
        historyDiv.innerHTML = '<p>Chargement...</p>';
        openModal(conversationModal);
        try {
            const response = await fetch(`/api/admin/leads/${visitorId}/conversations`);
            if (!response.ok) throw new Error('Erreur réseau');
            const conversations = await response.json();
            historyDiv.innerHTML = '';
            if (conversations.length === 0) { historyDiv.innerHTML = '<p>Aucun historique trouvé.</p>'; return; }
            conversations.forEach(msg => {
                const msgEl = document.createElement('div');
                msgEl.className = `p-3 rounded-lg mb-2 ${msg.role === 'user' ? 'bg-blue-100 dark:bg-blue-900' : 'bg-gray-100 dark:bg-gray-700'}`;
                msgEl.innerHTML = `<strong class="block text-sm capitalize font-bold">${msg.role}</strong><span class="text-xs text-gray-500">${new Date(msg.created_at).toLocaleString('fr-FR')}</span><p class="mt-1">${msg.content}</p>`;
                historyDiv.appendChild(msgEl);
            });
        } catch (error) { historyDiv.innerHTML = `<p>Erreur: ${error.message}</p>`; }
    };

    const handleEditClick = (visitorId) => {
        const lead = state.allLeads.find(l => l.visitor_id === visitorId);
        if (!lead) return;
        document.getElementById('edit-visitor-id').value = lead.visitor_id;
        document.getElementById('edit-name').value = lead.name || '';
        document.getElementById('edit-email').value = lead.email || '';
        document.getElementById('edit-phone').value = lead.phone || '';
        openModal(editLeadModal);
    };

    const handleEditFormSubmit = async (e) => {
        e.preventDefault();
        const visitorId = document.getElementById('edit-visitor-id').value;
        const updatedData = {
            name: document.getElementById('edit-name').value,
            email: document.getElementById('edit-email').value,
            phone: document.getElementById('edit-phone').value,
        };
        try {
            const response = await fetch(`/api/admin/leads/${visitorId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updatedData),
            });
            if (!response.ok) throw new Error('La mise à jour a échoué');
            const updatedLead = await response.json();
            // Update local state
            const index = state.allLeads.findIndex(l => l.visitor_id === visitorId);
            if (index !== -1) state.allLeads[index] = updatedLead;
            render();
            closeModal(editLeadModal);
        } catch (error) {
            alert(`Erreur: ${error.message}`);
        }
    };

    // --- INITIALIZATION ---
    const init = async () => {
        // Theme
        if (localStorage.getItem('theme') === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
            darkIcon.classList.add('hidden'); lightIcon.classList.remove('hidden');
        }
        themeToggle.addEventListener('click', () => {
            document.documentElement.classList.toggle('dark');
            darkIcon.classList.toggle('hidden'); lightIcon.classList.toggle('hidden');
            localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
        });

        // SPA Nav
        const showSection = (id) => {
            sections.forEach(s => s.id === `${id}-section` ? s.classList.remove('hidden') : s.classList.add('hidden'));
            navLinks.forEach(l => l.dataset.section === id ? l.classList.add('bg-gray-200', 'dark:bg-gray-700') : l.classList.remove('bg-gray-200', 'dark:bg-gray-700'));
        };
        const updateView = () => showSection(window.location.hash.substring(1) || 'home');
        navLinks.forEach(link => link.addEventListener('click', (e) => { e.preventDefault(); window.location.hash = link.dataset.section; }));
        window.addEventListener('hashchange', updateView);
        updateView();

        // Data Fetch
        try {
            const [statsRes, leadsRes] = await Promise.all([fetch('/api/admin/stats'), fetch('/api/admin/leads')]);
            if (!statsRes.ok || !leadsRes.ok) throw new Error('Échec du chargement des données initiales');
            const statsData = await statsRes.json();
            const leadsData = await leadsRes.json();
            totalLeadsEl.textContent = statsData.total_leads;
            renderLeadsChart(statsData.leads_over_time);
            state.allLeads = leadsData;
            render();
        } catch (error) {
            console.error(error);
            document.querySelector('main').innerHTML = `<p class="text-red-500 p-10">${error.message}. Vérifiez la console.</p>`;
        }

        // Event Listeners
        searchFilter.addEventListener('input', () => { state.currentPage = 1; render(); });
        sortableHeaders.forEach(header => header.addEventListener('click', (e) => {
            const newSortColumn = e.currentTarget.dataset.sort;
            if (state.sortColumn === newSortColumn) { state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc'; }
            else { state.sortColumn = newSortColumn; state.sortDirection = 'asc'; }
            state.currentPage = 1; render();
        }));
        paginationControls.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') { state.currentPage = parseInt(e.target.dataset.page); render(); }
        });
        leadsTbody.addEventListener('click', e => {
            const target = e.target;
            if (target.classList.contains('history-button')) handleHistoryClick(target.dataset.visitorId, target.dataset.leadName);
            if (target.classList.contains('edit-button')) handleEditClick(target.dataset.visitorId);
        });
        document.querySelectorAll('.close-button').forEach(btn => btn.addEventListener('click', () => {
            closeModal(document.getElementById(btn.dataset.modalId));
        }));
        document.getElementById('edit-lead-form').addEventListener('submit', handleEditFormSubmit);

        feather.replace();
    };

    init();
});
