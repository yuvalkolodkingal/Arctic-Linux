.pragma library
.import "Icons.js" as Design
// Glyphs the Settings app needs that the design bundle (Icons.js, generated — do not edit)
// doesn't have yet. Same 24-unit grid, 1.75 stroke, round caps and joins (brand book
// "Iconography"); move them into the design system when it grows them.
var EXTRA = {
 "display": "<rect x=\"3\" y=\"4.5\" width=\"18\" height=\"12\" rx=\"2\"/><path d=\"M9 20h6 M12 16.5V20\"/>",
 "mouse": "<rect x=\"6.5\" y=\"3\" width=\"11\" height=\"18\" rx=\"5.5\"/><path d=\"M12 3v5.5\"/>",
 "accessibility": "<circle cx=\"12\" cy=\"12\" r=\"8.5\"/><circle cx=\"12\" cy=\"7.6\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/><path d=\"M8 10.3l4 .9 4-.9 M12 11.2v3.1 M12 14.3l-2 3.7 M12 14.3l2 3.7\"/>"
};
function svg(name, color, stroke) {
    if (!Object.prototype.hasOwnProperty.call(EXTRA, name))
        return Design.svg(name, color, stroke);
    var body = EXTRA[name].replace(/currentColor/g, color);
    var s = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="' + color +
        '" stroke-width="' + (stroke || 1.75) + '" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>";
    return "data:image/svg+xml;utf8," + encodeURIComponent(s);
}
