.pragma library
// Safe arithmetic for the launcher's "=" mode. A small recursive-descent parser: numbers,
// + − × ÷ * / % ^, parentheses, unary minus, pi and e, and a few functions. It never
// evaluates JavaScript, so nothing typed here can run code.

const FUNCTIONS = {
    sqrt: Math.sqrt, abs: Math.abs, round: Math.round, floor: Math.floor, ceil: Math.ceil,
    sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan,
    ln: Math.log, log: Math.log10, exp: Math.exp
};
const CONSTANTS = { pi: Math.PI, e: Math.E };

function tokenize(text) {
    const tokens = [];
    const src = String(text).replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/\*\*/g, '^');
    let i = 0;
    while (i < src.length) {
        const ch = src[i];
        if (/\s/.test(ch)) { i++; continue; }
        if (/[0-9.]/.test(ch)) {
            let j = i;
            while (j < src.length && /[0-9._]/.test(src[j])) j++;
            if (j < src.length && /[eE]/.test(src[j]) && /[-+0-9]/.test(src[j + 1] || '')) {
                j++;
                if (/[-+]/.test(src[j])) j++;
                while (j < src.length && /[0-9]/.test(src[j])) j++;
            }
            const raw = src.slice(i, j).replace(/_/g, '');
            if (!/^(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(raw)) throw new Error('Check the number ' + raw);
            tokens.push({ type: 'num', value: parseFloat(raw) });
            i = j;
            continue;
        }
        if (/[a-zA-Z]/.test(ch)) {
            let j = i;
            while (j < src.length && /[a-zA-Z0-9]/.test(src[j])) j++;
            tokens.push({ type: 'name', value: src.slice(i, j).toLowerCase() });
            i = j;
            continue;
        }
        if ('+-*/%^(),'.indexOf(ch) >= 0) { tokens.push({ type: 'op', value: ch }); i++; continue; }
        throw new Error('Unexpected “' + ch + '”');
    }
    return tokens;
}

function parse(tokens) {
    let pos = 0;
    const peek = () => tokens[pos];
    const take = () => tokens[pos++];
    const isOp = (v) => peek() && peek().type === 'op' && peek().value === v;

    function expression() {
        let value = term();
        while (isOp('+') || isOp('-')) {
            const op = take().value, right = term();
            value = op === '+' ? value + right : value - right;
        }
        return value;
    }
    function term() {
        let value = unary();
        while (isOp('*') || isOp('/') || isOp('%') || (peek() && (peek().value === '(' || peek().type === 'name' || peek().type === 'num'))) {
            // Implicit multiplication: 2(3+4), 2pi
            const op = peek().type === 'op' && peek().value !== '(' ? take().value : '*';
            const right = unary();
            if (op === '*') value *= right;
            else if (op === '/') value /= right;
            else value %= right;
        }
        return value;
    }
    function unary() {
        if (isOp('-')) { take(); return -unary(); }
        if (isOp('+')) { take(); return unary(); }
        return power();
    }
    function power() {
        const base = primary();
        if (isOp('^')) { take(); return Math.pow(base, unary()); }
        return base;
    }
    function primary() {
        const t = take();
        if (!t) throw new Error('Incomplete expression');
        if (t.type === 'num') return t.value;
        if (t.type === 'name') {
            if (Object.prototype.hasOwnProperty.call(CONSTANTS, t.value)) return CONSTANTS[t.value];
            if (Object.prototype.hasOwnProperty.call(FUNCTIONS, t.value)) {
                if (!isOp('(')) throw new Error(t.value + ' needs brackets, like ' + t.value + '(2)');
                take();
                const arg = expression();
                if (!isOp(')')) throw new Error('Missing )');
                take();
                return FUNCTIONS[t.value](arg);
            }
            throw new Error('Unknown name “' + t.value + '”');
        }
        if (t.value === '(') {
            const value = expression();
            if (!isOp(')')) throw new Error('Missing )');
            take();
            return value;
        }
        throw new Error('Unexpected “' + t.value + '”');
    }
    const value = expression();
    if (pos < tokens.length) throw new Error('Unexpected “' + tokens[pos].value + '”');
    return value;
}

function format(value) {
    if (!isFinite(value)) return value > 0 ? '∞' : value < 0 ? '−∞' : 'Not a number';
    if (Math.abs(value) >= 1e15 || (value !== 0 && Math.abs(value) < 1e-9)) return value.toExponential(8).replace(/\.?0+e/, 'e');
    return String(parseFloat(value.toPrecision(12)));
}

// evaluate('2+2') -> {ok: true, value: 4, text: '4'} | {ok: false, error: '…'}
function evaluate(text) {
    try {
        if (!String(text).trim()) return { ok: false, error: 'Type a sum, like 12 * 4 + 1' };
        const value = parse(tokenize(text));
        if (typeof value !== 'number' || isNaN(value)) return { ok: false, error: 'That isn’t a number' };
        return { ok: true, value: value, text: format(value) };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}
