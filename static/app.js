/* VoiceMatch - Frontend Application */

// ---- Tab Navigation ----
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');

        if (tab.dataset.tab === 'database') {
            loadActors();
        }
    });
});

// ---- Loading Overlay ----
function showLoading(text = 'Analyse en cours...') {
    document.getElementById('loading-text').textContent = text;
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

// ---- Results Display ----
function showResults(results) {
    const container = document.getElementById('results');
    const list = document.getElementById('results-list');
    container.classList.remove('hidden');

    if (!results || results.length === 0) {
        list.innerHTML = '<div class="no-results">Aucune correspondance trouvee. Essayez d\'indexer plus de voix dans l\'onglet "Indexer des voix".</div>';
        return;
    }

    list.innerHTML = results.map((r, i) => `
        <div class="result-card">
            <div class="result-rank">#${i + 1}</div>
            <div class="result-info">
                <div class="result-name">${escapeHtml(r.name)}</div>
                ${r.original_actor ? `<div class="result-original">Voix de : ${escapeHtml(r.original_actor)}</div>` : ''}
                ${r.youtube_url ? `<div class="result-source"><a href="${escapeHtml(r.youtube_url)}" target="_blank">Voir la source YouTube</a></div>` : ''}
            </div>
            <div class="result-score">
                <div class="score-value">${r.similarity}%</div>
                <div class="score-label">similarite</div>
            </div>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ---- Microphone Recording ----
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;
let animationId = null;

const btnRecord = document.getElementById('btn-record');
const btnStop = document.getElementById('btn-stop');
const recordStatus = document.getElementById('record-status');
const canvas = document.getElementById('canvas-record');
const canvasCtx = canvas.getContext('2d');

btnRecord.addEventListener('click', startRecording);
btnStop.addEventListener('click', stopRecording);

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            cancelAnimationFrame(animationId);
            clearCanvas();

            if (audioChunks.length === 0) {
                recordStatus.textContent = 'Enregistrement vide';
                return;
            }

            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            await matchRecording(blob);
        };

        mediaRecorder.start();
        btnRecord.disabled = true;
        btnRecord.classList.add('recording');
        btnStop.disabled = false;
        recordStatus.textContent = 'Enregistrement en cours...';
        drawWaveform();

    } catch (err) {
        recordStatus.textContent = 'Erreur : acces au micro refuse';
        console.error('Microphone error:', err);
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    btnRecord.disabled = false;
    btnRecord.classList.remove('recording');
    btnStop.disabled = true;
    recordStatus.textContent = 'Analyse...';
}

function drawWaveform() {
    if (!analyser) return;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        animationId = requestAnimationFrame(draw);
        analyser.getByteTimeDomainData(dataArray);

        canvasCtx.fillStyle = '#0f0f1a';
        canvasCtx.fillRect(0, 0, canvas.width, canvas.height);

        canvasCtx.lineWidth = 2;
        canvasCtx.strokeStyle = '#6c5ce7';
        canvasCtx.beginPath();

        const sliceWidth = canvas.width / bufferLength;
        let x = 0;
        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 128.0;
            const y = (v * canvas.height) / 2;
            if (i === 0) canvasCtx.moveTo(x, y);
            else canvasCtx.lineTo(x, y);
            x += sliceWidth;
        }
        canvasCtx.lineTo(canvas.width, canvas.height / 2);
        canvasCtx.stroke();
    }
    draw();
}

function clearCanvas() {
    canvasCtx.fillStyle = '#0f0f1a';
    canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
}

async function matchRecording(blob) {
    showLoading('Analyse de l\'enregistrement...');
    try {
        const formData = new FormData();
        formData.append('file', blob, 'recording.webm');
        const resp = await fetch('/api/match/record', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        if (data.success) {
            showResults(data.results);
            recordStatus.textContent = `${data.results.length} resultat(s) trouve(s)`;
        } else {
            recordStatus.textContent = 'Erreur: ' + (data.detail || 'inconnue');
        }
    } catch (err) {
        hideLoading();
        recordStatus.textContent = 'Erreur reseau';
        console.error('Match error:', err);
    }
}

// ---- File Upload ----
document.getElementById('form-upload').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('input-file');
    if (!fileInput.files[0]) return;

    showLoading('Analyse du fichier audio...');
    try {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const resp = await fetch('/api/match/upload', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        if (data.success) {
            showResults(data.results);
        } else {
            alert('Erreur: ' + (data.detail || 'inconnue'));
        }
    } catch (err) {
        hideLoading();
        alert('Erreur reseau');
        console.error(err);
    }
});

// ---- YouTube Match ----
document.getElementById('form-youtube-match').addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = document.getElementById('input-yt-url').value.trim();
    if (!url) return;

    showLoading('Telechargement et analyse de la video YouTube...');
    try {
        const formData = new FormData();
        formData.append('url', url);
        const resp = await fetch('/api/match/youtube', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        if (data.success) {
            showResults(data.results);
        } else {
            alert('Erreur: ' + (data.detail || 'inconnue'));
        }
    } catch (err) {
        hideLoading();
        alert('Erreur reseau');
        console.error(err);
    }
});

// ---- Index URL ----
document.getElementById('form-index-url').addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = document.getElementById('input-index-url').value.trim();
    if (!url) return;

    showLoading('Indexation de la video...');
    const resultDiv = document.getElementById('index-url-result');
    try {
        const formData = new FormData();
        formData.append('url', url);
        const resp = await fetch('/api/index/url', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        resultDiv.classList.remove('hidden');
        if (data.success) {
            const info = data.indexed;
            resultDiv.innerHTML = `<div class="alert alert-success">
                Video indexee ! Doubleur : <strong>${escapeHtml(info.dubber)}</strong>
                ${info.original_actor ? ` (voix de ${escapeHtml(info.original_actor)})` : ''}
            </div>`;
            refreshStats();
        } else {
            resultDiv.innerHTML = `<div class="alert alert-error">${escapeHtml(data.detail || 'Erreur')}</div>`;
        }
    } catch (err) {
        hideLoading();
        resultDiv.classList.remove('hidden');
        resultDiv.innerHTML = `<div class="alert alert-error">Erreur reseau</div>`;
    }
});

// ---- Index Search ----
document.getElementById('form-index-search').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('input-search-query').value.trim();
    const maxVideos = document.getElementById('input-max-videos').value;

    showLoading('Recherche et indexation en cours... (cela peut prendre plusieurs minutes)');
    const resultDiv = document.getElementById('index-search-result');
    try {
        const formData = new FormData();
        formData.append('query', query);
        formData.append('max_videos', maxVideos);
        const resp = await fetch('/api/index/search', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        resultDiv.classList.remove('hidden');
        if (data.success) {
            resultDiv.innerHTML = `<div class="alert alert-success">
                ${data.indexed_count} video(s) indexee(s) avec succes !
            </div>`;
            if (data.indexed && data.indexed.length > 0) {
                resultDiv.innerHTML += '<div style="margin-top:12px">' +
                    data.indexed.map(v => `<div class="actor-item">
                        <div>
                            <div class="actor-name">${escapeHtml(v.dubber)}</div>
                            <div class="actor-original">${escapeHtml(v.original_actor || '')}</div>
                        </div>
                    </div>`).join('') + '</div>';
            }
            refreshStats();
        } else {
            resultDiv.innerHTML = `<div class="alert alert-error">${escapeHtml(data.detail || 'Erreur')}</div>`;
        }
    } catch (err) {
        hideLoading();
        resultDiv.classList.remove('hidden');
        resultDiv.innerHTML = `<div class="alert alert-error">Erreur reseau</div>`;
    }
});

// ---- Load Actors ----
async function loadActors() {
    const list = document.getElementById('actors-list');
    try {
        const resp = await fetch('/api/actors');
        const data = await resp.json();

        if (!data.actors || data.actors.length === 0) {
            list.innerHTML = '<p class="placeholder">Aucun acteur dans la base. Indexez des videos dans l\'onglet "Indexer des voix".</p>';
            return;
        }

        list.innerHTML = data.actors.map(a => `
            <div class="actor-item">
                <div>
                    <div class="actor-name">${escapeHtml(a.name)}</div>
                    <div class="actor-original">${a.original_actor ? 'Voix de : ' + escapeHtml(a.original_actor) : ''}</div>
                </div>
                <div class="actor-samples">${a.sample_count} echantillon(s)</div>
            </div>
        `).join('');
    } catch (err) {
        list.innerHTML = '<p class="placeholder">Erreur de chargement</p>';
    }
}

document.getElementById('btn-refresh-actors').addEventListener('click', loadActors);

// ---- Refresh Stats ----
async function refreshStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        document.getElementById('stat-actors').textContent = data.actors;
        document.getElementById('stat-samples').textContent = data.voice_samples;
    } catch (err) {
        // ignore
    }
}
