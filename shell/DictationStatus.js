.pragma library
// Only status crosses this boundary. Transcribed text and captured audio never enter QML.
// Canonical parser for the desktop indicator and Settings. Quickshell confines imports
// to each config root: settings/DictationStatus.js bundles these identical bytes.
// settings/tests/test_app_files.py rejects drift; RPM installs this canonical source.

function parse(text) {
    let data;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    const out = { state: 'unavailable', ready: false, progress: 0, error: '', profile: '', model: '',
                  model_download_bytes: 0, download_bytes: 0, cpu_variant: '', active_cpu_variant: '',
                  language: 'auto', backend: 'auto', active_backend: '', profile_selection: '',
                  compatibility_required: false, recommended_profile: profileDescriptor(null),
                  compatibility_profile: profileDescriptor(null) };
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    if (['unavailable', 'queued', 'downloading', 'ready', 'recording', 'transcribing', 'error'].includes(data.state))
        out.state = data.state;
    const progress = Number(data.progress);
    if (Number.isFinite(progress)) out.progress = Math.max(0, Math.min(1, progress));
    // The controller emits fixed actionable errors, never upstream output or transcripts.
    if (typeof data.error === 'string') out.error = data.error.slice(0, 1000);
    for (const key of ['model_download_bytes', 'download_bytes']) {
        const value = data[key];
        if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0) out[key] = value;
    }
    if (['small-v2', 'turbo-q5-v3'].includes(data.profile)) out.profile = data.profile;
    if (['small', 'large-v3-turbo-q5_0'].includes(data.model)) out.model = data.model;
    if (['baseline', 'avx2'].includes(data.cpu_variant)) out.cpu_variant = data.cpu_variant;
    if (['auto', 'he', 'en'].includes(data.language)) out.language = data.language;
    if (['auto', 'cpu', 'vulkan'].includes(data.backend)) out.backend = data.backend;
    if (['cpu', 'vulkan'].includes(data.active_backend)) out.active_backend = data.active_backend;
    if (out.active_backend === 'cpu' && ['baseline', 'avx2'].includes(data.active_cpu_variant))
        out.active_cpu_variant = data.active_cpu_variant;
    if (['recommended', 'compatibility'].includes(data.profile_selection)) out.profile_selection = data.profile_selection;
    out.compatibility_required = data.compatibility_required === true;
    out.recommended_profile = profileDescriptor(data.recommended_profile);
    out.compatibility_profile = profileDescriptor(data.compatibility_profile);
    if (out.compatibility_profile.profile !== 'small-v2') out.compatibility_profile = profileDescriptor(null);
    if (!profileKnown(out)) {
        // An unknown descriptor must never silently become a Small download disclosure.
        out.profile = ''; out.model = ''; out.cpu_variant = '';
        out.model_download_bytes = 0; out.download_bytes = 0;
        if (!out.error) out.error = 'The hardware profile or download sizes are unavailable. Cancel any active recording, then refresh status or install the latest Arctic updates.';
        // Preserve an active privacy indicator even if its descriptor is malformed.
        if (!active(out)) out.state = 'error';
    }
    out.ready = profileKnown(out) && !out.compatibility_required && data.ready === true
        && ['ready', 'recording', 'transcribing', 'error'].includes(out.state);
    if (out.compatibility_required && !active(out)) {
        out.state = 'error';
        if (!out.error) out.error = 'Set up the compatibility model before recording again.';
    }
    return out;
}

function profileDescriptor(data) {
    const out = { profile: '', model: '', cpu_variant: '', model_download_bytes: 0, download_bytes: 0 };
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    if (['small-v2', 'turbo-q5-v3'].includes(data.profile)) out.profile = data.profile;
    if (['small', 'large-v3-turbo-q5_0'].includes(data.model)) out.model = data.model;
    if (['baseline', 'avx2'].includes(data.cpu_variant)) out.cpu_variant = data.cpu_variant;
    for (const key of ['model_download_bytes', 'download_bytes']) {
        if (typeof data[key] === 'number' && Number.isSafeInteger(data[key]) && data[key] > 0) out[key] = data[key];
    }
    return profileKnown(out) ? out : { profile: '', model: '', cpu_variant: '', model_download_bytes: 0, download_bytes: 0 };
}

function profileKnown(status) {
    const valid = status.profile === 'small-v2' && status.model === 'small' && status.cpu_variant === 'baseline'
        || status.profile === 'turbo-q5-v3' && status.model === 'large-v3-turbo-q5_0' && status.cpu_variant === 'avx2';
    return valid && status.model_download_bytes > 0 && status.download_bytes >= status.model_download_bytes;
}

function modelTitle(status) {
    if (!profileKnown(status)) return 'Model unavailable';
    return status.model === 'small' ? 'Whisper Small multilingual' : 'Whisper Large v3 Turbo Q5 multilingual';
}

function setupDescription(status) {
    if (!profileKnown(status)) return 'Refresh status to obtain the hardware profile and download sizes before setup.';
    return modelTitle(status) + ': ' + size(status.model_download_bytes) + ' model. '
        + (status.profile === 'small-v2' ? 'Baseline CPU app and model: ' : 'Baseline CPU, AVX2 CPU, Vulkan support and model: ')
        + size(status.download_bytes) + ' download (' + status.download_bytes + ' bytes). Downloads are checked before use.';
}

function setupConsent(status) {
    if (!profileKnown(status)) return 'The hardware profile and download sizes are unavailable. Refresh status or update Arctic before retrying setup.';
    return 'The pinned app and model files total ' + size(status.download_bytes) + ' (' + status.download_bytes
        + ' bytes), including the ' + size(status.model_download_bytes) + ' ' + modelTitle(status)
        + ' model. Missing system packages may need additional downloads. An administrator password may be requested. '
        + 'Existing verified files can be reused. Setup failures remain retryable.';
}

function setupTarget(status, action) {
    if (action === 'retry') {
        // Queued/download progress describes its frozen job. A new retry resolves
        // the persisted selection again, including after a hardware migration.
        action = status.profile_selection === 'recommended' ? 'recommended-setup'
            : status.profile_selection === 'compatibility' ? 'compatibility-setup' : '';
    }
    if (action === 'recommended-setup') return profileDescriptor(status.recommended_profile);
    if (action === 'compatibility-setup') {
        const target = profileDescriptor(status.compatibility_profile);
        return target.profile === 'small-v2' ? target : profileDescriptor(null);
    }
    return profileDescriptor(null);
}

function accelerationDetail(status) {
    let text = !profileKnown(status) ? 'Refresh status to see the supported hardware profile.'
        : status.profile === 'small-v2' ? 'This hardware profile uses baseline CPU transcription. Automatic uses CPU; Vulkan is unavailable in this profile.'
        : 'Automatic uses supported Vulkan GPU acceleration with an AVX2 CPU fallback. After a GPU failure, follow the error and record again. '
            + 'If the optimized CPU engine is unsupported, explicitly set up the Small compatibility model below before recording again.';
    if (status.active_backend) text += ' Current backend: ' + (status.active_backend === 'vulkan' ? 'Vulkan GPU.'
        : status.active_cpu_variant === 'avx2' ? 'AVX2 CPU.' : status.active_cpu_variant === 'baseline' ? 'Baseline CPU.' : 'CPU.');
    return text + ' Accuracy and speed depend on your hardware and audio.';
}

function backends(status) {
    const choices = [{ value: 'auto', label: 'Automatic' }, { value: 'cpu', label: 'CPU' }];
    if (status.profile === 'turbo-q5-v3') choices.push({ value: 'vulkan', label: 'Vulkan GPU' });
    else if (status.backend === 'vulkan') choices.push({ value: 'vulkan', label: 'Vulkan GPU (unavailable)' });
    return choices;
}

function selectionDetail(status) {
    if (status.compatibility_required) return 'The optimized CPU engine is unsupported. Download and verify the Small compatibility model before recording again.';
    if (status.profile_selection === 'compatibility') return 'Compatibility is selected: Whisper Small uses baseline CPU. Return to the recommendation only after reviewing its model and download sizes.';
    if (status.profile_selection === 'recommended') return 'The recommendation follows this computer\'s CPU capabilities. You can explicitly choose the Small compatibility model if the recommended engine cannot run.';
    return 'Refresh status to see the selected hardware profile.';
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
