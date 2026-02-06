/* VoiceMatch - Public Frontend (Shazam-like) */

// ---- Screen Navigation ----
function showScreen(id) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(id).classList.add('active');
}

// ---- Loading Overlay ----
function showLoading(text) {
    document.getElementById('loading-text').textContent = text || 'Analyse en cours...';
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

// ---- HTML Escaping ----
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ---- Microphone Recording ----
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;
let animationId = null;
let isRecording = false;

const btnListen = document.getElementById('btn-listen');
const listenLabel = document.getElementById('listen-label');
const waveformContainer = document.getElementById('waveform-container');
const canvas = document.getElementById('canvas-waveform');
const canvasCtx = canvas.getContext('2d');

btnListen.addEventListener('click', toggleRecording);

async function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

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
                listenLabel.textContent = 'Enregistrement vide';
                return;
            }

            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            await matchRecording(blob);
        };

        mediaRecorder.start();
        isRecording = true;
        btnListen.classList.add('listening');
        listenLabel.textContent = 'Ecoute en cours... Appuyez pour arreter';
        waveformContainer.classList.remove('hidden');
        drawWaveform();

    } catch (err) {
        listenLabel.textContent = 'Erreur : acces au micro refuse';
        console.error('Microphone error:', err);
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    btnListen.classList.remove('listening');
    listenLabel.textContent = 'Analyse...';
    waveformContainer.classList.add('hidden');
}

function drawWaveform() {
    if (!analyser) return;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        animationId = requestAnimationFrame(draw);
        analyser.getByteTimeDomainData(dataArray);

        canvasCtx.fillStyle = 'rgba(15, 15, 26, 0.3)';
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

// ---- Match from Recording ----
async function matchRecording(blob) {
    showLoading('Analyse de la voix...');
    try {
        const formData = new FormData();
        formData.append('file', blob, 'recording.webm');
        const resp = await fetch('/api/match/record', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        if (data.success) {
            displayResults(data.results);
        } else {
            listenLabel.textContent = 'Erreur: ' + (data.detail || 'inconnue');
        }
    } catch (err) {
        hideLoading();
        listenLabel.textContent = 'Erreur reseau';
        console.error('Match error:', err);
    }
}

// ---- File Upload Match ----
document.getElementById('input-file-match').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    showLoading('Analyse du fichier audio...');
    try {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch('/api/match/upload', { method: 'POST', body: formData });
        const data = await resp.json();
        hideLoading();

        if (data.success) {
            displayResults(data.results);
        } else {
            alert('Erreur: ' + (data.detail || 'inconnue'));
        }
    } catch (err) {
        hideLoading();
        alert('Erreur reseau');
        console.error(err);
    }
    // Reset file input
    e.target.value = '';
});

// ---- Display Results ----
function displayResults(results) {
    const container = document.getElementById('results-container');
    showScreen('screen-results');

    if (!results || results.length === 0) {
        container.innerHTML = `
            <div class="no-results-card">
                <div class="no-results-icon">?</div>
                <h2>Aucune correspondance</h2>
                <p>La voix n'a pas ete reconnue dans notre base de donnees.</p>
            </div>`;
        return;
    }

    // Show the best match prominently, then others below
    const best = results[0];
    const others = results.slice(1);

    container.innerHTML = `
        <div id="best-match" class="best-match-card">
            <div class="match-score">${best.similarity}%</div>
            <h2 class="match-name">${escapeHtml(best.name)}</h2>
            ${best.original_actor ? `<p class="match-role">Voix de ${escapeHtml(best.original_actor)}</p>` : ''}
            <div id="wiki-info" class="wiki-info loading-wiki">
                <div class="wiki-spinner"></div>
                <span>Recherche d'informations...</span>
            </div>
        </div>
        ${others.length > 0 ? `
            <h3 class="other-matches-title">Autres correspondances</h3>
            ${others.map(r => `
                <div class="other-match-card">
                    <div class="other-match-info">
                        <span class="other-match-name">${escapeHtml(r.name)}</span>
                        ${r.original_actor ? `<span class="other-match-role"> - voix de ${escapeHtml(r.original_actor)}</span>` : ''}
                    </div>
                    <div class="other-match-score">${r.similarity}%</div>
                </div>
            `).join('')}
        ` : ''}
    `;

    // Fetch Wikipedia info for the best match
    fetchWikipediaInfo(best.name);
}

// ---- Fetch Wikipedia Info ----
async function fetchWikipediaInfo(actorName) {
    const wikiDiv = document.getElementById('wiki-info');
    try {
        const resp = await fetch(`/api/wikipedia/${encodeURIComponent(actorName)}`);
        const data = await resp.json();

        if (data.success && data.info) {
            const info = data.info;
            wikiDiv.classList.remove('loading-wiki');
            wikiDiv.innerHTML = `
                ${info.thumbnail ? `<img src="${escapeHtml(info.thumbnail)}" alt="${escapeHtml(info.title)}" class="wiki-thumb" />` : ''}
                <div class="wiki-text">
                    ${info.description ? `<p class="wiki-desc">${escapeHtml(info.description)}</p>` : ''}
                    ${info.extract ? `<p class="wiki-extract">${escapeHtml(info.extract)}</p>` : ''}
                    ${info.url ? `<a href="${escapeHtml(info.url)}" target="_blank" rel="noopener" class="wiki-link">Voir sur Wikipedia</a>` : ''}
                </div>
            `;
        } else {
            wikiDiv.classList.remove('loading-wiki');
            wikiDiv.innerHTML = '<p class="wiki-not-found">Aucune information Wikipedia trouvee.</p>';
        }
    } catch (err) {
        wikiDiv.classList.remove('loading-wiki');
        wikiDiv.innerHTML = '<p class="wiki-not-found">Impossible de charger les informations.</p>';
        console.error('Wikipedia fetch error:', err);
    }
}

// ---- Back Button ----
document.getElementById('btn-back').addEventListener('click', () => {
    showScreen('screen-main');
    listenLabel.textContent = 'Appuyez pour identifier une voix';
    document.getElementById('results-container').innerHTML = '';
});
