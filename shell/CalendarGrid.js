.pragma library
// The calendar panel's month grid, as pure functions (tests/test-calendar-grid.cjs).
// Months are 0-based as in JavaScript; `firstDay` is the first day of the week, 0 = Sunday …
// 6 = Saturday (QML's Locale.firstDayOfWeek; 7 is read as Sunday too).

function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// ISO 8601 week number: weeks start on Monday, week 1 holds the year's first Thursday.
function isoWeek(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const day = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

function daysIn(year, month) {
    return new Date(year, month + 1, 0).getDate();
}

// Six weeks of seven days covering the month: [{week, days: [{date, day, inMonth, isToday}]}].
function monthGrid(year, month, firstDay, today) {
    const first = ((firstDay % 7) + 7) % 7;
    const start = new Date(year, month, 1);
    const lead = (start.getDay() - first + 7) % 7;
    const rows = [];
    for (let w = 0; w < 6; w++) {
        const days = [];
        for (let d = 0; d < 7; d++) {
            const date = new Date(year, month, 1 - lead + w * 7 + d);
            days.push({ date: date, day: date.getDate(), inMonth: date.getMonth() === month,
                        isToday: !!today && sameDay(date, today) });
        }
        // The ISO week of the row's Thursday-most day: the week most of the row belongs to.
        rows.push({ week: isoWeek(days[(4 - first + 7) % 7].date), days: days });
    }
    return rows;
}

// Move a date by days or months, keeping the day within the target month (31 Jan + 1 month = 28/29 Feb).
function addDays(date, n) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}
function addMonths(date, n) {
    const target = new Date(date.getFullYear(), date.getMonth() + n, 1);
    return new Date(target.getFullYear(), target.getMonth(), Math.min(date.getDate(), daysIn(target.getFullYear(), target.getMonth())));
}
