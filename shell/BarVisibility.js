.pragma library

// Mango IPC rectangles and output geometry are both global logical coordinates, including
// fractional scaling and negative output origins. Touching the boundary is not an overlap.
function overlaps(monitors, windows, name, edge, thickness) {
    const m = monitors.find(item => item.name === name);
    if (!m || m.width <= 0 || m.height <= 0) return false;
    const t = Math.min(thickness, edge === 'left' || edge === 'right' ? m.width : m.height);
    const region = { x: m.x, y: m.y, width: m.width, height: m.height };
    if (edge === 'left' || edge === 'right') {
        region.width = t;
        if (edge === 'right') region.x += m.width - t;
    } else {
        region.height = t;
        if (edge === 'bottom') region.y += m.height - t;
    }
    return windows.some(w => w.x < region.x + region.width && w.x + w.width > region.x
        && w.y < region.y + region.height && w.y + w.height > region.y);
}
