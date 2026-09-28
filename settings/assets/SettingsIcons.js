.pragma library
.import "Icons.js" as Design
// Glyphs the Settings app needs that the design bundle (Icons.js, generated — do not edit)
// doesn't have yet. Same 24-unit grid, 1.75 stroke, round caps and joins (brand book
// "Iconography"); move them into the design system when it grows them.
var EXTRA = {
 "display": "<rect x=\"3\" y=\"4.5\" width=\"18\" height=\"12\" rx=\"2\"/><path d=\"M9 20h6 M12 16.5V20\"/>",
 "mouse": "<rect x=\"6.5\" y=\"3\" width=\"11\" height=\"18\" rx=\"5.5\"/><path d=\"M12 3v5.5\"/>",
 "printer": "<path d=\"M7 8.5V3.5h10v5 M7 17H5a2 2 0 0 1-2-2v-4.5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2V15a2 2 0 0 1-2 2h-2\"/><rect x=\"7\" y=\"13.5\" width=\"10\" height=\"7\" rx=\"1\"/>"
};
function svg(name, color, stroke) {
    if (!Object.prototype.hasOwnProperty.call(EXTRA, name))
        return Design.svg(name, color, stroke);
    var body = EXTRA[name].replace(/currentColor/g, color);
    var s = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="' + color +
        '" stroke-width="' + (stroke || 1.75) + '" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>";
    return "data:image/svg+xml;utf8," + encodeURIComponent(s);
}
