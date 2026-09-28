// The arctic-webapp serve wire format as the shell speaks it: node shell/tests/test-webapp-protocol.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../WebAppProtocol.js', 'utf8').replace('.pragma library', ''), context);
const P = context;
const plain = value => JSON.parse(JSON.stringify(value));

assert.equal(P.request(3, 'Remove', { ids: ['org.arcticlinux.WebApp.Music_4c1a9e'], keep_data: true }),
             '{"id":3,"method":"Remove","params":{"ids":["org.arcticlinux.WebApp.Music_4c1a9e"],"keep_data":true}}\n');
assert.equal(P.request(0, 'Hello'), '{"id":0,"method":"Hello","params":{}}\n');

assert.deepEqual(plain(P.parse('{"event":"progress","request":1,"stage":"manifest","message":"Reading the app manifest"}')),
                 { kind: 'progress', request: 1, stage: 'manifest', message: 'Reading the app manifest' });
assert.deepEqual(plain(P.parse('{"event":"changed","ids":["a"]}')), { kind: 'changed', ids: ['a'] });
assert.deepEqual(plain(P.parse('{"id":2,"result":{"app":{"id":"x"}}}')), { kind: 'reply', id: 2, result: { app: { id: 'x' } }, error: null });
assert.deepEqual(plain(P.parse('{"id":4,"result":{}}')).result, {});
assert.deepEqual(plain(P.parse('{"id":1,"error":{"code":"offline","message":"You’re offline."}}')),
                 { kind: 'reply', id: 1, result: null, error: { code: 'offline', message: 'You’re offline.', fields: {} } });
assert.equal(P.parse('{"id":7,"error":{"code":"invalid","message":"Check the highlighted options.","fields":{"runtime":"Brave isn’t installed."}}}').error.fields.runtime,
             'Brave isn’t installed.');
assert.equal(P.parse('{"event":"later","id":3}').kind, 'ignore');          // an event, even with an id
assert.equal(P.parse('not json').kind, 'ignore');
assert.equal(P.parse('{"result":{}}').kind, 'ignore');                       // no id
assert.equal(P.parse('null').kind, 'ignore');

const runtimes = [{ id: 'webkit', name: 'Arctic', available: true }, { id: 'chromium:brave', name: 'Brave', available: true }];
assert.equal(P.runtimeName(runtimes, 'chromium:brave'), 'Brave');
assert.equal(P.runtimeName([], 'webkit'), 'Arctic');
assert.equal(P.runtimeName(runtimes, 'chromium:vivaldi'), '');
console.log('Web app protocol checks passed.');
