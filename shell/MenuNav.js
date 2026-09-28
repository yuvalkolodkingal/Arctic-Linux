.pragma library
// Keyboard movement inside a bar menu (MenuList), as pure functions (tests/test-menu-nav.cjs).
//
// `stops` is the ordered list of rows a menu can focus: objects with `enabled` (false = skipped),
// `label` (for type-ahead) and `group` (a number; Tab moves between groups: the header switch,
// the list, the footer). Every function returns an index into `stops`, or -1 when there is
// nothing to focus.

function usable(stop) {
    return !!stop && stop.enabled !== false;
}

// The next usable stop from `current` in direction `dir` (+1 / -1). Wraps by default; without
// wrapping it stays put at either end. From -1 it starts at the first (or last) usable stop.
function step(stops, current, dir, wrap) {
    const n = stops.length;
    if (!n) return -1;
    const around = wrap !== false;
    let i = current;
    if (i < 0 || i >= n) i = dir > 0 ? -1 : n;
    for (let k = 0; k < n; k++) {
        i += dir > 0 ? 1 : -1;
        if (i >= n || i < 0) {
            if (!around) return usable(stops[current]) ? current : -1;
            i = i >= n ? 0 : n - 1;
        }
        if (usable(stops[i])) return i;
    }
    return usable(stops[current]) ? current : -1;
}

// The first (dir -1) or last (dir +1) usable stop: Home and End.
function edge(stops, dir) {
    return step(stops, dir > 0 ? stops.length : -1, dir > 0 ? -1 : 1, false);
}

// `count` usable stops away without wrapping: PgUp / PgDn (5 rows).
function page(stops, current, dir, count) {
    let i = current;
    for (let k = 0; k < (count || 5); k++) {
        const next = step(stops, i, dir, false);
        if (next === i || next < 0) break;
        i = next;
    }
    return i;
}

// The first usable stop of the next (dir +1) or previous (dir -1) group: Tab / Shift+Tab.
// Wraps around; a menu with one group stays where it is.
function group(stops, current, dir) {
    const n = stops.length;
    if (!n) return -1;
    if (current < 0 || current >= n) return edge(stops, dir > 0 ? -1 : 1);
    const here = stops[current].group;
    let i = current;
    for (let k = 0; k < n; k++) {
        i = (i + (dir > 0 ? 1 : -1) + n) % n;
        if (!usable(stops[i]) || stops[i].group === here) continue;
        if (dir > 0) return i;
        // Backwards: land on the first stop of that group, not its last.
        let first = i;
        for (let j = i - 1; j >= 0 && stops[j].group === stops[i].group; j--) if (usable(stops[j])) first = j;
        return first;
    }
    return current;
}

// Type-ahead: the next usable stop after `from` whose label starts with `prefix` (case
// insensitive), wrapping; `from` itself only when nothing else matches. -1 when none does.
function match(stops, from, prefix) {
    const n = stops.length;
    const want = String(prefix || '').toLocaleLowerCase();
    if (!n || !want) return -1;
    for (let k = 1; k <= n; k++) {
        const i = ((from < 0 ? -1 : from) + k + n) % n;
        const label = String(stops[i] && stops[i].label || '').toLocaleLowerCase();
        if (usable(stops[i]) && label.indexOf(want) === 0) return i;
    }
    return -1;
}
