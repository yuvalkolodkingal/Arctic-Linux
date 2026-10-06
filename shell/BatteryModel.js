.pragma library

// Quickshell's UPower Percentage is a fraction (UPower's wire value / 100).
// Keep unknown readings distinct from an empty battery, and round the icon and
// text together: 99.5% is 100%, while a charge-limited 80% remains 80%.
function percentage(fraction) {
    if (typeof fraction !== 'number' || !isFinite(fraction) || fraction < 0) return -1;
    return Math.min(100, Math.round(fraction * 100));
}

function percentageText(percent) {
    return percent >= 0 ? percent + '%' : 'Charge unknown';
}
