.pragma library
// Sanitized setup/runtime state only. Audio and transcripts never enter QML.
function parse(text) {
    let data;
    try { data = JSON.parse(String(text || '')); } catch (_) { data = null; }
    const out = { state: 'unavailable', ready: false, error: '', language: 'auto', backend: 'cpu',
                  profile: '', model: '', model_download_bytes: 0, download_bytes: 0,
                  vulkan_download_bytes: 66575872 };
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    if (['unavailable', 'queued', 'downloading', 'ready', 'recording', 'transcribing', 'error'].includes(data.state)) out.state = data.state;
    if (typeof data.error === 'string') out.error = data.error.slice(0, 500);
    if (['auto', 'he', 'en'].includes(data.language)) out.language = data.language;
    if (['cpu', 'vulkan'].includes(data.backend)) out.backend = data.backend;
    if (['small-v2', 'turbo-q5-v3'].includes(data.profile)) out.profile = data.profile;
    if (['small', 'large-v3-turbo-q5_0'].includes(data.model)) out.model = data.model;
    for (const key of ['model_download_bytes', 'download_bytes', 'vulkan_download_bytes']) {
        if (Number.isSafeInteger(data[key]) && data[key] > 0) out[key] = data[key];
    }
    out.ready = data.ready === true && ['ready', 'recording', 'transcribing', 'error'].includes(out.state);
    return out;
}
function profileKnown(s) {
    return (s.profile === 'small-v2' && s.model === 'small' && s.model_download_bytes === 487601967 && s.download_bytes === 506440871)
        || (s.profile === 'turbo-q5-v3' && s.model === 'large-v3-turbo-q5_0' && s.model_download_bytes === 574041195 && s.download_bytes === 593457131);
}
function modelTitle(s) { return s.profile === 'small-v2' ? 'Whisper Small multilingual' : s.profile === 'turbo-q5-v3' ? 'Whisper Large v3 Turbo Q5 multilingual' : 'Whisper model'; }
function setupDescription(s) {
    if (!profileKnown(s)) return 'The installer selects a compatibility or modern local profile for this processor.';
    return modelTitle(s) + ': ' + size(s.model_download_bytes) + '. Signed VoxType and model download: ' + size(s.download_bytes) + ' (' + s.download_bytes + ' bytes).';
}
function setupConsent(s) {
    if (!profileKnown(s)) return 'Refresh status before setup.';
    return 'Download ' + size(s.download_bytes) + ' (' + s.download_bytes + ' bytes) for signed VoxType 1.1.1 and ' + modelTitle(s) + '. Files are verified before use; failure remains retryable.';
}
function setupTarget(s, action) { return action === 'retry' ? s : parse(''); }
function accelerationDetail(s) {
    const current = s.backend === 'vulkan' ? 'Vulkan is selected. If it fails, select CPU here; fallback is explicit.' : 'CPU is selected and remains the recovery path if Vulkan fails.';
    return current + ' Enabling Vulkan downloads ' + size(s.vulkan_download_bytes) + ' (' + s.vulkan_download_bytes + ' bytes).';
}
function backends(_) { return [{ value: 'cpu', label: 'CPU' }, { value: 'vulkan', label: 'Vulkan GPU' }]; }
function selectionDetail(s) { return profileKnown(s) ? modelTitle(s) : 'Profile unavailable'; }
function active(s) { return s.state === 'recording' || s.state === 'transcribing'; }
function headline(s) { return ({ unavailable:'Dictation is not ready', queued:'Dictation setup is queued', downloading:'Downloading dictation', ready:'Dictation is ready', recording:'Dictation is recording', transcribing:'Transcribing on this computer', error:'Dictation needs attention' })[s.state] || 'Dictation is not ready'; }
function detail(s) {
    if (s.error) return s.error;
    return ({ unavailable:'VoxType and a local model must be installed before recording.', queued:'Connect to the internet and retry setup.', downloading:'Downloading and verifying VoxType and the local model.', ready:'Focus a text field, then press Super + Ctrl + X to start or stop.', recording:'Audio stays on this computer. Press Super + Ctrl + X to stop, or cancel.', transcribing:'The local model is processing audio. Cancel with Super + Ctrl + Backspace.', error:'Retry setup or switch back to CPU acceleration.' })[s.state] || '';
}
function size(bytes) { return (bytes / 1000000).toFixed(1) + ' MB'; }
