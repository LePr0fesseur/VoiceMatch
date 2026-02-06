/* VoiceMatch - Admin Frontend */

document.addEventListener('DOMContentLoaded', () => {

    // ---- Screen Management ----
    function showAdminScreen(id) {
        document.querySelectorAll('.admin-screen').forEach(s => s.classList.remove('active'));
        const el = document.getElementById(id);
        if (el) el.classList.add('active');
    }

    function showAdminLoading() {
        const lo = document.getElementById('admin-loading');
        if (lo) lo.classList.remove('hidden');
    }

    function hideAdminLoading() {
        const lo = document.getElementById('admin-loading');
        if (lo) lo.classList.add('hidden');
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    // ---- Check Auth on Load ----
    async function checkAuth() {
        try {
            const resp = await fetch('/api/admin/check', { credentials: 'same-origin' });
            const data = await resp.json();
            if (data.authenticated) {
                showAdminScreen('dashboard-screen');
                if (data.default_password) {
                    document.getElementById('password-warning').classList.remove('hidden');
                }
                loadStats();
                loadActors();
            } else {
                showAdminScreen('login-screen');
            }
        } catch (err) {
            showAdminScreen('login-screen');
        }
    }

    checkAuth();

    // ---- Login ----
    const formLogin = document.getElementById('form-login');
    if (formLogin) {
        formLogin.addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = document.getElementById('input-password').value;
            const errorDiv = document.getElementById('login-error');
            errorDiv.classList.add('hidden');

            try {
                const formData = new FormData();
                formData.append('password', password);
                const resp = await fetch('/api/admin/login', {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin',
                });

                if (resp.ok) {
                    const data = await resp.json();
                    showAdminScreen('dashboard-screen');
                    if (data.default_password) {
                        document.getElementById('password-warning').classList.remove('hidden');
                    }
                    loadStats();
                    loadActors();
                } else {
                    const data = await resp.json();
                    errorDiv.textContent = data.detail || 'Mot de passe incorrect';
                    errorDiv.classList.remove('hidden');
                }
            } catch (err) {
                errorDiv.textContent = 'Erreur reseau';
                errorDiv.classList.remove('hidden');
            }
        });
    }

    // ---- Logout ----
    const btnLogout = document.getElementById('btn-logout');
    if (btnLogout) {
        btnLogout.addEventListener('click', async () => {
            await fetch('/api/admin/logout', { method: 'POST', credentials: 'same-origin' });
            showAdminScreen('login-screen');
            document.getElementById('input-password').value = '';
        });
    }

    // ---- Load Stats ----
    async function loadStats() {
        try {
            const resp = await fetch('/api/stats');
            const data = await resp.json();
            const sa = document.getElementById('admin-stat-actors');
            const ss = document.getElementById('admin-stat-samples');
            if (sa) sa.textContent = data.actors;
            if (ss) ss.textContent = data.voice_samples;
        } catch (err) {
            console.error('Stats error:', err);
        }
    }

    // ---- Upload MP3 ----
    const formUpload = document.getElementById('form-upload');
    if (formUpload) {
        formUpload.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('input-mp3');
            const dubberName = document.getElementById('input-dubber').value.trim();
            const resultDiv = document.getElementById('upload-result');

            if (!fileInput.files[0] || !dubberName) return;

            showAdminLoading();
            resultDiv.classList.add('hidden');

            try {
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                formData.append('dubber_name', dubberName);
                const resp = await fetch('/api/admin/upload', {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin',
                });
                const data = await resp.json();
                hideAdminLoading();

                resultDiv.classList.remove('hidden');
                if (resp.ok && data.success) {
                    resultDiv.innerHTML = `<div class="alert alert-success">
                        Voix ajoutee ! Doubleur : <strong>${escapeHtml(data.indexed.dubber)}</strong>
                    </div>`;
                    fileInput.value = '';
                    document.getElementById('input-dubber').value = '';
                    loadStats();
                    loadActors();
                } else {
                    resultDiv.innerHTML = `<div class="alert alert-error">${escapeHtml(data.detail || 'Erreur')}</div>`;
                }
            } catch (err) {
                hideAdminLoading();
                resultDiv.classList.remove('hidden');
                resultDiv.innerHTML = `<div class="alert alert-error">Erreur reseau</div>`;
            }
        });
    }

    // ---- Load Actors ----
    async function loadActors() {
        const list = document.getElementById('actors-list');
        if (!list) return;

        try {
            const resp = await fetch('/api/admin/actors', { credentials: 'same-origin' });
            if (!resp.ok) {
                list.innerHTML = '<p class="placeholder">Erreur d\'authentification</p>';
                return;
            }
            const data = await resp.json();

            if (!data.actors || data.actors.length === 0) {
                list.innerHTML = '<p class="placeholder">Aucun doubleur dans la base.</p>';
                return;
            }

            list.innerHTML = data.actors.map(a => `
                <div class="actor-item" data-id="${a.id}">
                    <div class="actor-info">
                        <div class="actor-name">${escapeHtml(a.name)}</div>
                        <div class="actor-meta">${a.sample_count} echantillon(s)</div>
                    </div>
                    <button class="btn btn-danger btn-sm btn-delete-actor" data-id="${a.id}" data-name="${escapeHtml(a.name)}">
                        Supprimer
                    </button>
                </div>
            `).join('');

            // Attach delete handlers
            list.querySelectorAll('.btn-delete-actor').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const actorId = btn.dataset.id;
                    const name = btn.dataset.name;
                    if (!confirm(`Supprimer le doubleur "${name}" et tous ses echantillons ?`)) return;

                    try {
                        const resp = await fetch(`/api/admin/actors/${actorId}`, {
                            method: 'DELETE',
                            credentials: 'same-origin',
                        });
                        if (resp.ok) {
                            loadActors();
                            loadStats();
                        } else {
                            const data = await resp.json();
                            alert(data.detail || 'Erreur');
                        }
                    } catch (err) {
                        alert('Erreur reseau');
                    }
                });
            });
        } catch (err) {
            list.innerHTML = '<p class="placeholder">Erreur de chargement</p>';
        }
    }

    // ---- Refresh ----
    const btnRefresh = document.getElementById('btn-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            loadStats();
            loadActors();
        });
    }

    // ---- Change Password ----
    const formPassword = document.getElementById('form-password');
    if (formPassword) {
        formPassword.addEventListener('submit', async (e) => {
            e.preventDefault();
            const currentPw = document.getElementById('input-current-pw').value;
            const newPw = document.getElementById('input-new-pw').value;
            const resultDiv = document.getElementById('password-result');

            if (!currentPw || !newPw) return;

            try {
                const formData = new FormData();
                formData.append('current_password', currentPw);
                formData.append('new_password', newPw);
                const resp = await fetch('/api/admin/change-password', {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin',
                });
                const data = await resp.json();

                resultDiv.classList.remove('hidden');
                if (resp.ok && data.success) {
                    resultDiv.innerHTML = '<div class="alert alert-success">Mot de passe modifie avec succes.</div>';
                    document.getElementById('input-current-pw').value = '';
                    document.getElementById('input-new-pw').value = '';
                    document.getElementById('password-warning').classList.add('hidden');
                } else {
                    resultDiv.innerHTML = `<div class="alert alert-error">${escapeHtml(data.detail || 'Erreur')}</div>`;
                }
            } catch (err) {
                resultDiv.classList.remove('hidden');
                resultDiv.innerHTML = `<div class="alert alert-error">Erreur reseau</div>`;
            }
        });
    }

});
