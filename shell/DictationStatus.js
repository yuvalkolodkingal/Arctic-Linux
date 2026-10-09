.pragma library
// Only status crosses this boundary. Transcribed text and captured audio never enter QML.
// Shared by the desktop indicator and Settings (which depends on arctic-shell).

function parse(text) {
    let data;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    const out = { state: 'unavailable', ready: false, progress: 0, error: '', model: 'small',
                  model_download_bytes: 487601967, download_bytes: 572524159,
                  language: 'auto', backend: 'auto', active_backend: '' };
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    if (['unavailable', 'queued', 'downloading', 'ready', 'recording', 'transcribing', 'error'].includes(data.state))
        out.state = data.state;
    out.ready = data.ready === true && ['ready', 'recording', 'transcribing', 'error'].includes(out.state);
    const progress = Number(data.progress);
    if (Number.isFinite(progress)) out.progress = Math.max(0, Math.min(1, progress));
    // The controller emits fixed actionable errors, never upstream output or transcripts.
    if (typeof data.error === 'string') out.error = data.error.slice(0, 1000);
    for (const key of ['model_download_bytes', 'download_bytes']) {
        const value = Number(data[key]);
        if (Number.isSafeInteger(value) && value > 0) out[key] = value;
    }
    if (data.model === 'small') out.model = data.model;
    if (['auto', 'he', 'en'].includes(data.language)) out.language = data.language;
    if (['auto', 'cpu', 'vulkan'].includes(data.backend)) out.backend = data.backend;
    if (['cpu', 'vulkan'].includes(data.active_backend)) out.active_backend = data.active_backend;
    return out;
}

function active(status) {
    return status.state === 'recording' || status.state === 'transcribing';
}

function headline(status) {
    return ({ unavailable: 'Dictation is not ready', queued: 'Dictation setup is queued',
              downloading: 'Downloading dictation', ready: 'Dictation is ready',
              recording: 'Dictation is recording', transcribing: 'Transcribing on this computer',
              error: 'Dictation needs attention' })[status.state] || 'Dictation is not ready';
}

function detail(status) {
    if (status.error) return status.error;
    return ({ unavailable: 'The local app and multilingual Whisper model must be installed before recording.',
              queued: 'Connect to the internet and retry setup. Recording stays unavailable until setup finishes.',
              downloading: 'Downloading and verifying the local app and multilingual model. You can keep using Arctic.',
              ready: 'Focus a text field, then press Super + Ctrl + X to start. Press it again to stop and insert text.',
              recording: 'Audio stays on this computer. Stop with Super + Ctrl + X, or cancel with Super + Ctrl + Backspace.',
              transcribing: 'Release the shortcut keys. The result goes into the focused text field. Super + Ctrl + Backspace cancels it.',
              error: 'Retry setup for missing dependencies, or review the microphone and acceleration settings before recording again.' })[status.state] || '';
}

function size(bytes) {
    return (bytes / 1000000).toFixed(1) + ' MB';
}
