// App tiles: node shell/tests/test-icons.cjs
// A web app (arctic-webapp, desktop id org.arcticlinux.WebApp.…) keeps its own icon even when
// its name matches a design tile ("Signal", "Steam", "Settings").
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function source(file) {
    return fs.readFileSync(__dirname + '/../assets/' + file, 'utf8').replace('.pragma library', '');
}
const data = {};
vm.createContext(data);
vm.runInContext(source('design-data.js'), data);
const icons = { Data: data };
vm.createContext(icons);
vm.runInContext(source('Icons.js').replace(/^\.import .*$/m, ''), icons);

assert.equal(icons.tileFor('org.arcticlinux.WebApp.Signal_1a2b3c', 'Signal'), '');
assert.equal(icons.tileFor('org.arcticlinux.WebApp.Steam_1a2b3c', 'Steam Store'), '');
assert.equal(icons.tileFor('org.arcticlinux.WebApp.Settings_00ff00', 'Account settings'), '');
assert.equal(icons.tileFor('org.signal.Signal', 'Signal'), 'signal');
assert.equal(icons.tileFor('com.valvesoftware.Steam', 'Steam'), 'steam');
assert.equal(icons.tileFor('org.arcticlinux.Settings', 'Arctic Settings'), 'settings');
console.log('test-icons: ok');
