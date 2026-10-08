const fs = require('fs'), vm = require('vm'), assert = require('assert');
const B = {};
vm.createContext(B);
vm.runInContext(fs.readFileSync(__dirname + '/../BarVisibility.js','utf8').replace('.pragma library',''), B);
const screen = {name:'eDP-1', x:1920, y:-200, width:1280, height:720};
const second = {name:'HDMI', x:0, y:0, width:1920, height:1080};
const box = (x,y,width=100,height=100) => ({x,y,width,height});
const test = (edge,windows,thickness=32,name='eDP-1') => B.overlaps([screen,second],windows,name,edge,thickness);
for (const edge of ['left','right','top','bottom']) {
    assert.equal(test(edge,[]),false);
    assert.equal(test(edge,[box(2000,0)]),false);
    assert.equal(test(edge,[box(1920,-200,1280,720)]),true); // fullscreen
    assert.equal(test(edge,[box(50,50)]),false); // independent output
    assert.equal(test(edge,[box(0,0)],32,'removed'),false);
}
assert.equal(test('left',[box(1952,0)]),false); // only touches
assert.equal(test('left',[box(1951,0)]),true);
assert.equal(test('left',[box(1970,0)],56),true); // thickness change
assert.equal(test('right',[box(3068,0)]),false);
assert.equal(test('right',[box(3069,0)]),true);
assert.equal(test('top',[box(2200,-168)]),false);
assert.equal(test('top',[box(2200,-169)]),true);
assert.equal(test('bottom',[box(2200,388)]),false);
assert.equal(test('bottom',[box(2200,389)]),true);
assert.equal(test('left',[box(1900,0)]),true); // window spans outputs
assert.equal(test('right',[box(1900,0)],32,'HDMI'),true);
console.log('bar visibility: all edges, boundaries, scaling, origins and outputs passed');
