// The calendar panel's month grid (CalendarGrid.js): node shell/tests/test-calendar-grid.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = { Date: Date, Math: Math };
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const G = load('CalendarGrid.js');
const ymd = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

// ---- ISO weeks ---------------------------------------------------------------------------------
assert.equal(G.isoWeek(new Date(2026, 8, 28)), 40);          // Monday 28 September 2026
assert.equal(G.isoWeek(new Date(2026, 11, 31)), 53);         // 2026 has 53 weeks
assert.equal(G.isoWeek(new Date(2027, 0, 3)), 53);           // Sunday 3 Jan 2027 still in W53
assert.equal(G.isoWeek(new Date(2027, 0, 4)), 1);
assert.equal(G.isoWeek(new Date(2024, 11, 30)), 1);          // Monday 30 Dec 2024 is 2025-W01
assert.equal(G.isoWeek(new Date(2021, 0, 1)), 53);           // Friday 1 Jan 2021 is 2020-W53

// ---- a month with Monday first ----------------------------------------------------------------
const today = new Date(2026, 8, 28, 14, 5);
const sep = G.monthGrid(2026, 8, 1, today);
assert.equal(sep.length, 6);
sep.forEach(r => assert.equal(r.days.length, 7));
assert.equal(ymd(sep[0].days[0].date), '2026-08-31');        // Monday before 1 September (a Tuesday)
assert.equal(sep[0].days[0].inMonth, false);
assert.equal(sep[0].days[1].day, 1);
assert.equal(sep[0].days[1].inMonth, true);
assert.equal(sep[0].week, 36);
const marked = [].concat(...sep.map(r => r.days)).filter(d => d.isToday);
assert.equal(marked.length, 1);
assert.equal(ymd(marked[0].date), '2026-09-28');
assert.equal(ymd(sep[5].days[6].date), '2026-10-11');

// ---- Sunday first -------------------------------------------------------------------------------
const sun = G.monthGrid(2026, 8, 0, today);
assert.equal(ymd(sun[0].days[0].date), '2026-08-30');
assert.equal(sun[0].days[2].day, 1);
assert.equal(sun[0].week, 36);                                // its Thursday (3 Sep) is in W36
assert.equal(G.monthGrid(2026, 8, 7, today)[0].days[0].day, 30);   // 7 = Sunday too

// ---- leap Februaries and the year's end --------------------------------------------------------
const feb28 = G.monthGrid(2028, 1, 1, null);
assert.equal([].concat(...feb28.map(r => r.days)).filter(d => d.inMonth).length, 29);
assert.equal([].concat(...G.monthGrid(2027, 1, 1, null).map(r => r.days)).filter(d => d.inMonth).length, 28);
assert.equal([].concat(...feb28.map(r => r.days)).some(d => d.isToday), false);
const dec = G.monthGrid(2026, 11, 1, null);
assert.equal(dec[4].week, 53);                                // 28 Dec – 3 Jan
assert.equal(G.daysIn(2024, 1), 29);

// ---- moving around -----------------------------------------------------------------------------
assert.equal(ymd(G.addDays(new Date(2026, 11, 31), 1)), '2027-01-01');
assert.equal(ymd(G.addMonths(new Date(2026, 0, 31), 1)), '2026-02-28');
assert.equal(ymd(G.addMonths(new Date(2028, 0, 31), 1)), '2028-02-29');
assert.equal(ymd(G.addMonths(new Date(2026, 8, 28), -12)), '2025-09-28');

console.log('calendar grid: ok');
