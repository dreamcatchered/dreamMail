
const tg = window.Telegram.WebApp;
tg.expand();

// Elements
const els = {
    app: document.getElementById('app'),
    loading: document.getElementById('loading'),
    dashboard: document.getElementById('dashboard'),
    emailView: document.getElementById('email-view'),
    settingsView: document.getElementById('settings-view'),
    adminView: document.getElementById('admin-view'),
    adminUserDetailView: document.getElementById('admin-user-detail-view'),
    
    // Dashboard
    userProfileBtn: document.getElementById('user-profile-btn'),
    userName: document.getElementById('user-name'),
    userAvatar: document.getElementById('user-avatar'),
    searchInput: document.getElementById('search-input'),
    aliasScroller: document.getElementById('alias-scroller'),
    createAliasBtn: document.getElementById('create-alias-btn'),
    emailsList: document.getElementById('emails-list'),
    paginationTrigger: document.getElementById('pagination-trigger'),
    
    // Mass Actions
    selectAllCheckbox: document.getElementById('select-all-checkbox'),
    massActions: document.getElementById('mass-actions'),
    deleteSelectedBtn: document.getElementById('delete-selected-btn'),
    selectedCount: document.getElementById('selected-count'),
    
    // Email View
    backButton: document.getElementById('back-button'),
    emailSubject: document.getElementById('email-subject'),
    emailDeleteBtn: document.getElementById('email-delete-btn'),
    emailFrom: document.getElementById('email-from'),
    emailDate: document.getElementById('email-date'),
    emailBody: document.getElementById('email-body'),
    
    // Settings
    settingsBackBtn: document.getElementById('settings-back-btn'),
    settingsList: document.getElementById('settings-list'),
    adminEntryPoint: document.getElementById('admin-entry-point'),
    openAdminBtn: document.getElementById('open-admin-btn'),
    
    // Admin
    adminBackBtn: document.getElementById('admin-back-btn'),
    adminUsersList: document.getElementById('admin-users-list'),
    
    // Admin Detail
    adminDetailBackBtn: document.getElementById('admin-detail-back-btn'),
    adminUserTitle: document.getElementById('admin-user-title'),
    adminBlockBtn: document.getElementById('admin-block-btn'),
    adminDeleteUserBtn: document.getElementById('admin-delete-user-btn'),
    adminUserAliases: document.getElementById('admin-user-aliases'),
    adminAddAliasBtn: document.getElementById('admin-add-alias-btn'),
    adminUserEmails: document.getElementById('admin-user-emails'),
    adminLoadMoreEmailsBtn: document.getElementById('admin-load-more-emails-btn'),
    
    // Info View
    infoBtn: document.getElementById('info-btn'),
    infoView: document.getElementById('info-view'),
    infoBackBtn: document.getElementById('info-back-btn'),
    
    // Modal
    createModal: document.getElementById('create-modal'),
    newAliasLocal: document.getElementById('new-alias-local'),
    newAliasDomain: document.getElementById('new-alias-domain'),
    cancelCreate: document.getElementById('cancel-create'),
    confirmCreate: document.getElementById('confirm-create'),
    
    error: document.getElementById('error')
};

// State
let currentUser = null;
let currentAlias = 'Все';
let currentPage = 1; // UI Page (1-based)
const ITEMS_PER_PAGE = 20; // Must match backend limit if fixed, or be handled
let isLoadingEmails = false;
let hasMoreEmails = true;
let totalEmails = 0;
let adminEmailsPage = 0;

const ADMIN_ID = 669994046;
let adminTargetUserId = null; // For creating alias for another user
let adminUsersData = [];
let adminUserEmailsData = [];
let selectedEmailUids = new Set();
let currentEmailsData = []; // To track loaded emails for select all

// Init
async function init() {
    try {
        const res = await fetch('/api/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        });
        
        if (res.status === 403) {
            document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;color:red;"><h1>⛔️ Доступ запрещен</h1><p>Вы заблокированы администратором.</p></div>';
            return;
        }
        
        const data = await res.json();
        
        if (data.status === 'ok') {
            currentUser = data.user;
            setupUI();
            loadDashboard();
        } else {
            showError();
        }
    } catch (e) {
        console.error(e);
        showError();
    }
}

function setupUI() {
    els.emailsListContainer = document.querySelector('.emails-list-container');
    initDragToScroll();
    initKeyboardNav();

    // Elements
    els.prevPageBtn = document.getElementById('prev-page-btn');
    els.nextPageBtn = document.getElementById('next-page-btn');
    els.pageIndicator = document.getElementById('page-indicator');
    els.infoLink = document.getElementById('info-link');
    els.infoView = document.getElementById('info-view');
    els.infoBackBtn = document.getElementById('info-back-btn');
    
    // Listeners
    els.prevPageBtn.onclick = () => changePage(-1);
    els.nextPageBtn.onclick = () => changePage(1);
    els.infoLink.onclick = (e) => { e.preventDefault(); showScreen(els.infoView); };
    els.infoBackBtn.onclick = () => showScreen(els.dashboard);

    els.userProfileBtn.onclick = openSettings;
    els.backButton.onclick = () => showScreen(els.dashboard);
    els.settingsBackBtn.onclick = () => showScreen(els.dashboard);
    els.adminBackBtn.onclick = openSettings;
    els.adminDetailBackBtn.onclick = openAdmin;
    
    // Mass Actions Handlers
    els.selectAllCheckbox.onchange = (e) => toggleSelectAll(e.target.checked);
    els.deleteSelectedBtn.onclick = deleteSelectedEmails;
    els.emailDeleteBtn.onclick = () => {
        const uid = els.emailDeleteBtn.dataset.uid;
        if (uid) deleteUserEmail(uid, true);
    };

    els.createAliasBtn.onclick = () => openCreateModal(); // Changed to function
    els.cancelCreate.onclick = () => els.createModal.style.display = 'none';
    els.confirmCreate.onclick = createAlias;
    
    // Admin Button Visibility
    if (currentUser.id == ADMIN_ID) {
        els.openAdminBtn.style.display = 'block';
        els.openAdminBtn.onclick = openAdmin;
    } else {
        els.openAdminBtn.style.display = 'none';
    }
    
    // Search debounce
    let timeout;
    els.searchInput.addEventListener('input', (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            currentPage = 1;
            els.emailsList.innerHTML = '';
            currentEmailsData = [];
            selectedEmailUids.clear();
            updateMassActionsUI();
            hasMoreEmails = true;
            loadEmails(currentAlias, 0, e.target.value);
        }, 500);
    });
}

function showScreen(screen) {
    [els.dashboard, els.emailView, els.settingsView, els.adminView, els.adminUserDetailView, els.infoView, els.loading, els.error].forEach(el => el.style.display = 'none');
    screen.style.display = 'block';
    if (screen === els.dashboard) {
        els.dashboard.style.display = 'grid'; // Restore grid
        // Check PC layout and move search
        adjustPCLayout();
    }
}

function adjustPCLayout() {
    if (window.innerWidth >= 768) {
        const pcSearchPlaceholder = document.getElementById('pc-search-placeholder');
        const mobileSearchContainer = document.getElementById('mobile-search-container');
        const searchInput = document.getElementById('search-input');
        
        if (pcSearchPlaceholder && mobileSearchContainer && searchInput) {
            // Move search input to PC placeholder if not already there
            if (!pcSearchPlaceholder.contains(searchInput)) {
                pcSearchPlaceholder.style.display = 'block';
                pcSearchPlaceholder.appendChild(searchInput);
                mobileSearchContainer.style.display = 'none';
            }
        }
    } else {
        const pcSearchPlaceholder = document.getElementById('pc-search-placeholder');
        const mobileSearchContainer = document.getElementById('mobile-search-container');
        const searchInput = document.getElementById('search-input');
        
        if (pcSearchPlaceholder && mobileSearchContainer && searchInput) {
            // Move back to mobile container
            if (!mobileSearchContainer.contains(searchInput)) {
                mobileSearchContainer.style.display = 'block';
                mobileSearchContainer.appendChild(searchInput);
                pcSearchPlaceholder.style.display = 'none';
            }
        }
    }
}

// Listen to resize
window.addEventListener('resize', () => {
    if (els.dashboard.style.display !== 'none') {
        adjustPCLayout();
    }
});

function showError() {
    [els.loading, els.dashboard].forEach(el => el.style.display = 'none');
    els.error.style.display = 'flex';
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }
    return d.toLocaleDateString([], {day: 'numeric', month: 'short'});
}

function formatSender(sender) {
    // Remove <email> and quotes
    return sender.replace(/<[^>]*>/g, '').replace(/"/g, '').trim();
}

// --- Dashboard ---

async function loadDashboard() {
    showScreen(els.loading);
    try {
        const res = await fetch('/api/dashboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            els.userName.textContent = data.user_name || currentUser.first_name;
            
            // Avatar logic: Try Telegram unsafe first (more reliable for photo_url), then fallback
            const photoUrl = tg.initDataUnsafe?.user?.photo_url || currentUser.photo_url;
            if (photoUrl) {
                els.userAvatar.src = photoUrl;
            } else {
                // If no avatar, maybe set a default or just leave empty (browser shows alt or broken icon depending on handling)
                // Assuming CSS handles empty src or we set a placeholder?
                // If user said "remains display of first letter", maybe they want the photo to work.
            }
            
            renderAliases(data.aliases);
            showScreen(els.dashboard);
            
            // Initial load
    currentPage = 1;
    els.emailsList.innerHTML = '';
    currentEmailsData = [];
    selectedEmailUids.clear();
    updateMassActionsUI();
    loadEmails(); // Will use default page=0 (API) which is page=1 (UI)
}
    } catch (e) {
        console.error(e);
    }
}

function renderAliases(aliases) {
    els.aliasScroller.innerHTML = '';
    
    // "All" pill
    const allPill = document.createElement('div');
    allPill.className = `alias-pill ${currentAlias === 'Все' ? 'active' : ''}`;
    allPill.textContent = 'Все';
    allPill.onclick = () => switchAlias('Все');
    els.aliasScroller.appendChild(allPill);
    
    aliases.forEach(a => {
        const pill = document.createElement('div');
        pill.className = `alias-pill ${currentAlias === a.addr ? 'active' : ''}`;
        pill.textContent = a.addr; // Just address
        if (!a.active) pill.style.opacity = '0.6';
        pill.onclick = () => switchAlias(a.addr);
        els.aliasScroller.appendChild(pill);
    });
}

function switchAlias(alias) {
    currentAlias = alias;
    // Re-render pills to update active class
    const pills = els.aliasScroller.querySelectorAll('.alias-pill');
    pills.forEach(p => {
        if (p.textContent === alias) p.classList.add('active');
        else p.classList.remove('active');
    });
    
    currentPage = 1;
    els.emailsList.innerHTML = '';
    currentEmailsData = [];
    selectedEmailUids.clear();
    updateMassActionsUI();
    hasMoreEmails = true;
    loadEmails(alias);
}

// --- Emails ---

async function loadEmails(alias = currentAlias, page = currentPage - 1, search = '') {
    isLoadingEmails = true;
    updatePaginationUI(); // Disable buttons while loading
    
    try {
        const res = await fetch('/api/emails', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                initData: tg.initData,
                alias: alias === 'Все' ? null : alias,
                page: page,
                search: search
            })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            // Update total logic
            totalEmails = data.total;
            const totalPages = Math.ceil(totalEmails / ITEMS_PER_PAGE) || 1;
            
            // Check if we have more pages
            if (currentPage < totalPages) hasMoreEmails = true;
            else hasMoreEmails = false;

            // Clear list for pagination
            els.emailsList.innerHTML = '';
            currentEmailsData = data.emails; // Replace, don't append
            selectedEmailUids.clear(); // Clear selection on page change
            updateMassActionsUI();
            
            renderEmails(data.emails);
            updatePaginationUI();
        }
    } catch (e) {
        console.error(e);
    } finally {
        isLoadingEmails = false;
        updatePaginationUI();
    }
}

function changePage(delta) {
    if (isLoadingEmails) return;
    const newPage = currentPage + delta;
    if (newPage < 1) return;
    if (delta > 0 && !hasMoreEmails) return;

    currentPage = newPage;
    loadEmails();
}

function updatePaginationUI() {
    const totalPages = Math.ceil(totalEmails / ITEMS_PER_PAGE) || 1;
    if (els.pageIndicator) els.pageIndicator.textContent = `Стр. ${currentPage} из ${totalPages}`;
    
    if (els.prevPageBtn) {
        els.prevPageBtn.disabled = currentPage <= 1 || isLoadingEmails;
        // Hide previous button if on first page as requested ("на первой странице не должно быть стрелки назад")
        if (currentPage <= 1) els.prevPageBtn.style.visibility = 'hidden';
        else els.prevPageBtn.style.visibility = 'visible';
    }
    
    if (els.nextPageBtn) {
        els.nextPageBtn.disabled = currentPage >= totalPages || isLoadingEmails;
        if (currentPage >= totalPages) els.nextPageBtn.style.visibility = 'hidden';
        else els.nextPageBtn.style.visibility = 'visible';
    }
}

function renderEmails(emails) {
    if (!emails || emails.length === 0) {
        if (currentPage === 1) {
            els.emailsList.innerHTML = '<div style="text-align:center; padding: 20px; color: #888;">Писем пока нет</div>';
        }
        return;
    }
    
    emails.forEach(email => {
        const li = document.createElement('li');
        li.className = 'email-item';
        makeEmailsFocusable(li); // Make it focusable for keyboard nav
        // Click on item opens email, unless clicked on checkbox
        li.onclick = (e) => {
            if (e.target.type !== 'checkbox') {
                openEmail(email.uid);
            }
        };
        
        const isSelected = selectedEmailUids.has(email.uid);
        
        li.innerHTML = `
            <input type="checkbox" class="email-checkbox" data-uid="${email.uid}" ${isSelected ? 'checked' : ''}>
            <div class="email-content" style="padding-left: 0;">
                <div class="email-header">
                    <span class="email-sender">${formatSender(email.from)}</span>
                    <span class="email-date">${formatDate(email.date)}</span>
                </div>
                <div class="email-subject">${email.subject || '(Без темы)'}</div>
                <div class="email-preview">Нажмите, чтобы прочитать</div>
            </div>
        `;
        
        // Checkbox listener
        const cb = li.querySelector('.email-checkbox');
        cb.onchange = (e) => toggleEmailSelection(email.uid, e.target.checked);
        
        els.emailsList.appendChild(li);
    });
}

function toggleEmailSelection(uid, checked) {
    if (checked) {
        selectedEmailUids.add(uid);
    } else {
        selectedEmailUids.delete(uid);
    }
    updateMassActionsUI();
}

function toggleSelectAll(checked) {
    const checkboxes = els.emailsList.querySelectorAll('.email-checkbox');
    
    if (!checked) {
        // Deselect all
        selectedEmailUids.clear();
        checkboxes.forEach(cb => cb.checked = false);
    } else {
        // Select all currently loaded
        checkboxes.forEach(cb => cb.checked = true);
        currentEmailsData.forEach(e => selectedEmailUids.add(e.uid));
    }
    
    updateMassActionsUI();
}

// Drag to Scroll Implementation
function initDragToScroll() {
    const container = els.emailsListContainer; // The container, not the UL
    if (!container) return;

    let isDown = false;
    let startY;
    let scrollTop;

    container.addEventListener('mousedown', (e) => {
        isDown = true;
        container.style.cursor = 'grabbing';
        startY = e.pageY - container.offsetTop;
        scrollTop = container.scrollTop;
    });

    container.addEventListener('mouseleave', () => {
        isDown = false;
        container.style.cursor = 'default'; // Or grab
    });

    container.addEventListener('mouseup', () => {
        isDown = false;
        container.style.cursor = 'default'; // Or grab
    });

    container.addEventListener('mousemove', (e) => {
        if (!isDown) return;
        e.preventDefault();
        const y = e.pageY - container.offsetTop;
        const walk = (y - startY) * 2; // Scroll speed
        container.scrollTop = scrollTop - walk;
    });
}

// Keyboard Navigation
function initKeyboardNav() {
    document.addEventListener('keydown', (e) => {
        if (els.emailView.style.display !== 'none' || els.settingsView.style.display !== 'none' || els.infoView.style.display !== 'none') return;
        
        // Focus management? 
        // Let's implement simple selection navigation
        // Find currently focused or first email
        const items = Array.from(els.emailsList.querySelectorAll('.email-item'));
        if (items.length === 0) return;

        const focused = document.activeElement.closest('.email-item');
        let index = items.indexOf(focused);

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = items[index + 1] || items[0];
            next.focus();
            next.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = items[index - 1] || items[items.length - 1];
            prev.focus();
            prev.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            if (focused) {
                // If not clicking checkbox
                // Simulating click logic:
                // But we need to know UID.
                // The click handler is on LI.
                focused.click();
            }
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
            if (selectedEmailUids.size > 0) {
                deleteSelectedEmails();
            }
        }
    });
}

// Helper to make emails focusable
function makeEmailsFocusable(li) {
    li.setAttribute('tabindex', '0');
    // Add visual style for focus in CSS or standard outline
}

// --- API Interactions ---

function updateMassActionsUI() {
    const count = selectedEmailUids.size;
    els.selectedCount.textContent = `${count} выбрано`;
    
    if (count > 0) {
        els.massActions.style.display = 'flex';
    } else {
        els.massActions.style.display = 'none';
    }
    
    // Update master checkbox state if all selected
    els.selectAllCheckbox.checked = (currentEmailsData.length > 0 && count === currentEmailsData.length);
}

async function deleteSelectedEmails() {
    if (selectedEmailUids.size === 0) return;
    if (!confirm(`Удалить выбранные письма (${selectedEmailUids.size})?`)) return;
    
    // Deleting one by one or batch? API likely supports one by one.
    // For better UX, let's do parallel or batch if possible.
    // Assuming API is one by one for now based on deleteUserEmail.
    
    showScreen(els.loading);
    
    const uids = Array.from(selectedEmailUids);
    const promises = uids.map(uid => 
        fetch('/api/delete_email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, uid: uid })
        })
    );
    
    try {
        await Promise.all(promises);
        // Reset and reload
        selectedEmailUids.clear();
        updateMassActionsUI();
        els.selectAllCheckbox.checked = false;
        
        currentPage = 0;
        els.emailsList.innerHTML = '';
        currentEmailsData = [];
        loadEmails(currentAlias);
        
        showScreen(els.dashboard);
    } catch (e) {
        console.error(e);
        alert('Ошибка при удалении');
        showScreen(els.dashboard);
    }
}

async function deleteUserEmail(uid, fromView = false) {
    if (!confirm('Удалить это письмо?')) return;
    
    try {
        const res = await fetch('/api/delete_email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, uid: uid })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            if (fromView) {
                showScreen(els.dashboard);
            }
            // Reload emails
            currentPage = 0;
            els.emailsList.innerHTML = '';
            currentEmailsData = [];
            selectedEmailUids.clear();
            updateMassActionsUI();
            loadEmails(currentAlias);
        } else {
            alert('Ошибка удаления');
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка удаления');
    }
}

async function openEmail(uid, fromAdmin = false) {
    try {
        els.emailDeleteBtn.dataset.uid = uid; // Set UID for delete button
        const res = await fetch('/api/email_body', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, uid: uid })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            els.emailSubject.textContent = data.subject || '(Без темы)';
            
            // Show full From (Name + Email) but without brackets if possible, or just raw
            // User requested: "Ona ranshe byla v <> no ya poprosil ubrat lish skobki a ne samu pochtu..."
            // So if it's "Name <email>", we want "Name email"
            // If it's "email", we want "email"
            let fromText = data.from;
            if (fromText) {
                fromText = fromText.replace(/</g, ' ').replace(/>/g, '');
            }
            els.emailFrom.textContent = fromText;
            
            els.emailDate.textContent = formatDate(data.date || new Date()); // Date might be missing in body response if not passed
            
            // Prefer HTML, fallback to text
            if (data.html_body) {
                // Sanitize or frame it? For now direct injection
                els.emailBody.innerHTML = data.html_body;
            } else {
                els.emailBody.textContent = data.text_body;
            }
            
            // Adjust Back Button behavior
            if (fromAdmin) {
                els.backButton.onclick = () => showScreen(els.adminUserDetailView);
            } else {
                els.backButton.onclick = () => showScreen(els.dashboard);
            }

            showScreen(els.emailView);
        }
    } catch (e) {
        console.error(e);
    }
}

// --- Settings ---

async function openSettings() {
    showScreen(els.loading);
    
    // Check Admin
    if (currentUser.id === ADMIN_ID) {
        els.adminEntryPoint.style.display = 'block';
    }
    
    try {
        const res = await fetch('/api/dashboard', { // Re-use dashboard for aliases
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            renderSettings(data.aliases);
            showScreen(els.settingsView);
        }
    } catch (e) {
        console.error(e);
        showScreen(els.dashboard);
    }
}

function renderSettings(aliases) {
    els.settingsList.innerHTML = '';
    
    aliases.forEach((alias, index) => {
        const item = document.createElement('div');
        item.className = 'settings-item';
        
        // Status Text
        const statusText = alias.active ? 'Уведомления ВКЛ' : 'Уведомления ВЫКЛ';
        const statusColor = alias.active ? '#4CAF50' : '#FF5252';
        
        item.innerHTML = `
            <div class="settings-info">
                <div class="settings-alias">${alias.addr}</div>
                <div class="settings-status" style="color:${statusColor}">${statusText}</div>
            </div>
            <div class="settings-actions">
                <button class="btn-toggle">${alias.active ? 'Выкл' : 'Вкл'}</button>
                ${index === 0 ? '' : '<button class="btn-delete">Удалить</button>'}
            </div>
        `;
        
        item.querySelector('.btn-toggle').onclick = () => toggleAlias(alias.addr);
        if (index !== 0) {
            item.querySelector('.btn-delete').onclick = () => deleteAlias(alias.addr);
        }
        
        els.settingsList.appendChild(item);
    });
}

async function toggleAlias(alias) {
    try {
        const res = await fetch('/api/toggle_alias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, alias: alias })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            openSettings(); // Refresh
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteAlias(alias) {
    if (!confirm(`Удалить ящик ${alias}? Все письма будут потеряны.`)) return;
    try {
        const res = await fetch('/api/delete_alias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, alias: alias })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            openSettings();
        } else {
            alert('Ошибка удаления');
        }
    } catch (e) {
        console.error(e);
    }
}

function openCreateModal(targetId = null) {
    adminTargetUserId = targetId;
    els.newAliasLocal.value = '';
    // If we had domain selection, we could set it here.
    // For now assuming default or user selection.
    els.createModal.style.display = 'flex';
}

async function createAlias() {
    const local = els.newAliasLocal.value.trim();
    const domain = els.newAliasDomain.value;
    if (!local) return;
    
    const fullAlias = `${local}@${domain}`;
    
    // Check if we are creating for another user (Admin mode)
    if (adminTargetUserId) {
        try {
            const res = await fetch('/api/admin/add_alias', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: tg.initData, user_id: adminTargetUserId, alias: fullAlias })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                els.createModal.style.display = 'none';
                openAdminUserDetail(adminTargetUserId);
            } else {
                alert("Ошибка: " + (data.error || "Unknown"));
            }
        } catch (e) {
            console.error(e);
            alert("Ошибка сети");
        }
        return;
    }

    // Normal User Mode
    try {
        const res = await fetch('/api/create_alias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, alias: fullAlias })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            els.createModal.style.display = 'none';
            els.newAliasLocal.value = '';
            // Refresh logic? If on settings, reload settings. If dashboard, reload dashboard.
            // But usually we go back to dashboard
            loadDashboard();
        } else {
            alert('Ошибка: ' + (data.error || 'Unknown'));
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка сети');
    }
}

// --- Admin ---

async function openAdmin() {
    showScreen(els.loading);
    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            renderAdminUsers(data.users);
            showScreen(els.adminView);
        } else {
            alert('Доступ запрещен');
            showScreen(els.dashboard);
        }
    } catch (e) {
        console.error(e);
        showScreen(els.dashboard);
    }
}

function renderAdminUsers(users) {
    adminUsersData = users;
    els.adminUsersList.innerHTML = '';
    
    // Search Bar
    const searchDiv = document.createElement('div');
    searchDiv.style.marginBottom = '15px';
    searchDiv.innerHTML = `
        <input type="text" placeholder="Поиск (ID, имя, username)..." 
               style="width:100%; padding:12px; border-radius:12px; border:none; background:rgba(255,255,255,0.1); color:white; font-size:16px;">
    `;
    const searchInput = searchDiv.querySelector('input');
    searchInput.oninput = (e) => {
        const q = e.target.value.toLowerCase();
        const filtered = adminUsersData.filter(u => 
            (u.username && u.username.toLowerCase().includes(q)) ||
            (u.first_name && u.first_name.toLowerCase().includes(q)) ||
            (u.last_name && u.last_name.toLowerCase().includes(q)) ||
            String(u.user_id).includes(q)
        );
        renderAdminUsersList(filtered, listDiv);
    };
    
    els.adminUsersList.appendChild(searchDiv);
    
    // List Container
    const listDiv = document.createElement('div');
    els.adminUsersList.appendChild(listDiv);
    
    renderAdminUsersList(users, listDiv);
}

function renderAdminUsersList(users, container) {
    container.innerHTML = '';
    users.forEach(user => {
        const item = document.createElement('div');
        item.className = 'settings-item';
        
        const name = user.first_name ? `${user.first_name} ${user.last_name||''}` : `User ${user.user_id}`;
        const username = user.username ? `@${user.username}` : '';
        const blocked = user.is_blocked ? '<span style="color:red">[BLOCKED]</span>' : '';
        
        item.innerHTML = `
            <div class="settings-info">
                <div class="settings-alias">${name} ${username}</div>
                <div class="settings-status">ID: ${user.user_id} ${blocked}</div>
                <div class="settings-status" style="font-size:12px">Ящиков: ${user.alias_count} | Писем: ${user.email_count}</div>
            </div>
            <div class="settings-actions">
                <button class="btn-primary">Инфо</button>
            </div>
        `;
        
        item.querySelector('button').onclick = () => openAdminUserDetail(user.user_id);
        container.appendChild(item);
    });
}

async function openAdminUserDetail(userId) {
    showScreen(els.loading);
    try {
        const res = await fetch('/api/admin/user_details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            renderAdminUserDetail(data.details);
            // Also load emails
            loadAdminUserEmails(userId, true);
            showScreen(els.adminUserDetailView);
        }
    } catch (e) {
        console.error(e);
    }
}

function renderAdminUserDetail(user) {
    els.adminUserTitle.textContent = `${user.first_name || ''} ${user.last_name || ''} (${user.user_id})`;
    
    // Clear previous Telegram Info if exists
    const prevInfo = els.adminUserTitle.parentNode.querySelectorAll('.admin-tg-info');
    prevInfo.forEach(el => el.remove());

    // Show Telegram Info more explicitly
    const tgInfoDiv = document.createElement('div');
    tgInfoDiv.className = 'admin-tg-info'; // Add class for selection
    tgInfoDiv.style.padding = '10px';
    tgInfoDiv.style.marginBottom = '10px';
    tgInfoDiv.style.background = 'rgba(255,255,255,0.05)';
    tgInfoDiv.style.borderRadius = '10px';
    tgInfoDiv.innerHTML = `
        <p><strong>Username:</strong> ${user.username ? '@'+user.username : 'Нет'}</p>
        <p><strong>Имя:</strong> ${user.first_name || '-'}</p>
        <p><strong>Фамилия:</strong> ${user.last_name || '-'}</p>
    `;
    // Insert after title
    els.adminUserTitle.parentNode.insertBefore(tgInfoDiv, els.adminUserTitle.nextSibling);

    // Block Button
    els.adminBlockBtn.textContent = user.is_blocked ? 'Разблокировать' : 'Блокировать';
    els.adminBlockBtn.onclick = () => adminBlockUser(user.user_id, !user.is_blocked);
    
    // Delete User Button
    els.adminDeleteUserBtn.onclick = () => adminDeleteUser(user.user_id);
    
    // Aliases
    els.adminUserAliases.innerHTML = '';
    user.aliases.forEach(alias => {
        const item = document.createElement('div');
        item.className = 'settings-item';
        const statusText = alias.active ? 'Увед. ВКЛ' : 'Увед. ВЫКЛ';
        item.innerHTML = `
            <div class="settings-info">
                <div class="settings-alias">${alias.addr}</div>
                <div class="settings-status">${statusText}</div>
            </div>
            <div class="settings-actions">
                <button class="btn-toggle">${alias.active ? 'Выкл' : 'Вкл'}</button>
            </div>
        `;
        item.querySelector('.btn-toggle').onclick = () => adminToggleAlias(user.user_id, alias.addr);
        els.adminUserAliases.appendChild(item);
    });
    
    els.adminAddAliasBtn.onclick = () => openCreateModal(user.user_id);
    
    // Store current viewed user ID for pagination
    els.adminLoadMoreEmailsBtn.dataset.userId = user.user_id;
}

async function adminBlockUser(userId, block) {
    if (!confirm(block ? "Заблокировать пользователя?" : "Разблокировать пользователя?")) return;
    try {
        const res = await fetch('/api/admin/block_user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId, block: block })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            openAdminUserDetail(userId);
        }
    } catch (e) {
        console.error(e);
    }
}

async function adminDeleteUser(userId) {
    if (!confirm("ВНИМАНИЕ: Удалить пользователя? Это удалит ВСЕ его ящики и письма безвозвратно.")) return;
    
    try {
        const res = await fetch('/api/admin/delete_user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            alert("Пользователь удален");
            openAdmin(); // Go back to list
        } else {
            alert("Ошибка удаления");
        }
    } catch (e) {
        console.error(e);
        alert("Ошибка сети");
    }
}

async function adminToggleAlias(userId, alias) {
    try {
        const res = await fetch('/api/admin/toggle_alias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId, alias: alias })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            openAdminUserDetail(userId);
        }
    } catch (e) {
        console.error(e);
    }
}

async function adminAddAlias(userId) {
    const aliasLocal = prompt("Введите имя ящика (без домена):");
    if (!aliasLocal) return;
    // Default domain? Or ask? Assuming first domain for now or asking
    const domain = "dreampartners.online"; // Hardcoded or ask
    const fullAlias = `${aliasLocal}@${domain}`;
    
    try {
        const res = await fetch('/api/admin/add_alias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId, alias: fullAlias })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            openAdminUserDetail(userId);
        } else {
            alert("Ошибка: " + (data.error || "Unknown"));
        }
    } catch (e) {
        console.error(e);
    }
}

// --- Admin Emails ---

async function loadAdminUserEmails(userId, reset = false) {
    if (reset) {
        adminEmailsPage = 0;
        adminUserEmailsData = [];
        els.adminUserEmails.innerHTML = '';
    }
    
    try {
        const res = await fetch('/api/admin/user_emails', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, user_id: userId, page: adminEmailsPage })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            if (reset) {
                adminUserEmailsData = data.emails;
            } else {
                adminUserEmailsData = adminUserEmailsData.concat(data.emails);
            }
            
            renderAdminUserEmailsUI(userId);
            
            if (data.emails.length === 50) {
                els.adminLoadMoreEmailsBtn.style.display = 'block';
                els.adminLoadMoreEmailsBtn.onclick = () => {
                    adminEmailsPage++;
                    loadAdminUserEmails(userId);
                };
            } else {
                els.adminLoadMoreEmailsBtn.style.display = 'none';
            }
        }
    } catch (e) {
        console.error(e);
        if (reset) els.adminUserEmails.innerHTML = 'Ошибка загрузки писем';
    }
}

function renderAdminUserEmailsUI(userId) {
    let searchInput = els.adminUserEmails.querySelector('input');
    let listDiv = els.adminUserEmails.querySelector('.admin-email-list-container');
    
    if (!searchInput) {
        els.adminUserEmails.innerHTML = ''; 
        
        const searchDiv = document.createElement('div');
        searchDiv.style.marginBottom = '15px';
        searchDiv.innerHTML = `
            <input type="text" placeholder="Поиск по письмам..." 
                   style="width:100%; padding:12px; border-radius:12px; border:none; background:rgba(255,255,255,0.1); color:white; font-size:16px;">
        `;
        searchInput = searchDiv.querySelector('input');
        
        listDiv = document.createElement('div');
        listDiv.className = 'admin-email-list-container';
        
        els.adminUserEmails.appendChild(searchDiv);
        els.adminUserEmails.appendChild(listDiv);
        
        searchInput.oninput = () => {
             applyEmailFilter(searchInput.value, listDiv, userId);
        };
    }
    
    applyEmailFilter(searchInput.value, listDiv, userId);
}

function applyEmailFilter(query, container, userId) {
    const q = query.toLowerCase();
    const filtered = adminUserEmailsData.filter(email => 
             (email.subject && email.subject.toLowerCase().includes(q)) ||
             (email.from && email.from.toLowerCase().includes(q)) ||
             (email.to && email.to.toLowerCase().includes(q))
    );
    
    if (filtered.length === 0) {
        container.innerHTML = '<div style="padding:10px; color:#888;">Нет писем</div>';
        return;
    }
    
    renderAdminEmailItems(filtered, container, userId);
}

function renderAdminEmailItems(emails, container, userId) {
    container.innerHTML = '';
    emails.forEach(email => {
        const item = document.createElement('div');
        item.className = 'settings-item';
        
        item.innerHTML = `
            <div class="settings-info" style="overflow:hidden; cursor:pointer;">
                <div class="settings-alias" style="font-size:12px; color:#888;">${formatSender(email.from)} -> ${email.to}</div>
                <div class="settings-status" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                    ${email.subject || '(Без темы)'}
                </div>
                <div style="font-size:10px; color:#aaa;">${formatDate(email.date)}</div>
            </div>
            <div class="settings-actions">
                <button class="btn-delete">Удалить</button>
            </div>
        `;
        
        item.querySelector('.settings-info').onclick = () => openEmail(email.uid, true);

        const deleteBtn = item.querySelector('.btn-delete');
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            adminDeleteEmail(email.uid, deleteBtn);
        };
        
        container.appendChild(item);
    });
}

async function adminDeleteEmail(uid, btnElement) {
    if (!confirm("Удалить это письмо?")) return;
    
    try {
        const res = await fetch('/api/admin/delete_email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData, uid: uid })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            const item = btnElement.closest('.settings-item');
            item.remove();
        } else {
            alert("Ошибка удаления");
        }
    } catch (e) {
        console.error(e);
        alert("Ошибка сети");
    }
}

// Start
init();
