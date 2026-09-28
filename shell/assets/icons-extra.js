.pragma library
// Glyphs the bar menus need that the design bundle (design-data.js, generated — do not edit)
// doesn't have yet. Same 24-unit grid, 1.75 stroke (set by Icons.icon), round caps and joins,
// 2px corner radius on shapes, currentColor only for small filled dots. Move them into the
// design system when it grows them. `mouse` and `display` are byte-for-byte copies of
// settings/assets/SettingsIcons.js (tests/test-icons.cjs keeps the shared ones identical).
var EXTRA = {
 "wifi-1": "<path d=\"M9.9 16.3a3 3 0 0 1 4.2 0\"/><circle cx=\"12\" cy=\"19.3\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/>",
 "wifi-2": "<path d=\"M6.9 13.2a7.5 7.5 0 0 1 10.2 0 M9.9 16.3a3 3 0 0 1 4.2 0\"/><circle cx=\"12\" cy=\"19.3\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/>",
 "headphones": "<path d=\"M5 14.5V13a7 7 0 0 1 14 0v1.5\"/><rect x=\"3.5\" y=\"13.5\" width=\"3.5\" height=\"6.5\" rx=\"1.5\"/><rect x=\"17\" y=\"13.5\" width=\"3.5\" height=\"6.5\" rx=\"1.5\"/>",
 "headset": "<path d=\"M5 14.5V13a7 7 0 0 1 14 0v1.5 M5.3 20c0 1 .8 1.5 2 1.5H14\"/><rect x=\"3.5\" y=\"13.5\" width=\"3.5\" height=\"6.5\" rx=\"1.5\"/><rect x=\"17\" y=\"13.5\" width=\"3.5\" height=\"6.5\" rx=\"1.5\"/>",
 "speaker": "<rect x=\"6\" y=\"3\" width=\"12\" height=\"18\" rx=\"2\"/><circle cx=\"12\" cy=\"14.5\" r=\"3.5\"/><circle cx=\"12\" cy=\"7.5\" r=\"1\"/>",
 "display": "<rect x=\"3\" y=\"4.5\" width=\"18\" height=\"12\" rx=\"2\"/><path d=\"M9 20h6 M12 16.5V20\"/>",
 "mouse": "<rect x=\"6.5\" y=\"3\" width=\"11\" height=\"18\" rx=\"5.5\"/><path d=\"M12 3v5.5\"/>",
 "phone": "<rect x=\"7\" y=\"3\" width=\"10\" height=\"18\" rx=\"2\"/><path d=\"M11 18h2\"/>",
 "laptop": "<rect x=\"4\" y=\"5\" width=\"16\" height=\"10\" rx=\"2\"/><path d=\"M2 18h20\"/>",
 "pause": "<rect x=\"7\" y=\"6\" width=\"3\" height=\"12\" rx=\"1\"/><rect x=\"14\" y=\"6\" width=\"3\" height=\"12\" rx=\"1\"/>",
 "skip-back": "<path d=\"M18 6.5v11l-8.5-5.5z M6.5 6v12\"/>",
 "skip-forward": "<path d=\"M6 6.5v11l8.5-5.5z M17.5 6v12\"/>",
 "mic-off": "<rect x=\"9\" y=\"3.5\" width=\"6\" height=\"11\" rx=\"3\"/><path d=\"M5.5 11.5a6.5 6.5 0 0 0 13 0 M12 18v2.5 M4 4l16 16\"/>",
 "key": "<circle cx=\"8\" cy=\"15\" r=\"3.5\"/><path d=\"M10.5 12.5L19 4 M15.5 7.5l2.5 2.5 M17.5 5.5l2 2\"/>",
 "bell-dot": "<path d=\"M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z M10 20.5a2 2 0 0 0 4 0\"/><circle cx=\"18\" cy=\"6\" r=\"2.2\" fill=\"currentColor\" stroke=\"none\"/>",
 "leaf": "<path d=\"M5 19c0-8.5 5-13.5 14-14 0 9-5 14-13 14z M5 19l7.5-7.5\"/>",
 "gauge": "<path d=\"M4.6 17a8 8 0 1 1 14.8 0 M12 14l3.5-4\"/><circle cx=\"12\" cy=\"14\" r=\"1.2\" fill=\"currentColor\" stroke=\"none\"/>",
 "bolt": "<path d=\"M13 3L5.5 13.5H12L11 21l7.5-10.5H12z\"/>",
 "dots": "<circle cx=\"6\" cy=\"12\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"12\" cy=\"12\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"18\" cy=\"12\" r=\"1.1\" fill=\"currentColor\" stroke=\"none\"/>",
 "screen-share": "<rect x=\"3\" y=\"4.5\" width=\"18\" height=\"12\" rx=\"2\"/><path d=\"M9 20h6 M12 16.5V20 M12 13.5V8 M9.5 10.5L12 8l2.5 2.5\"/>",
 "sun": "<circle cx=\"12\" cy=\"12\" r=\"4\"/><path d=\"M12 2.5v2 M12 19.5v2 M2.5 12h2 M19.5 12h2 M5.3 5.3l1.4 1.4 M17.3 17.3l1.4 1.4 M5.3 18.7l1.4-1.4 M17.3 6.7l1.4-1.4\"/>",
 "airplane": "<path d=\"M12 3c.8 0 1.5.7 1.5 1.5V9.5l7 4v2l-7-2V18l2 1.5V21L12 20l-3.5 1v-1.5l2-1.5v-4.5l-7 2v-2l7-4V4.5C10.5 3.7 11.2 3 12 3z\"/>",
 "qr-code": "<rect x=\"3.5\" y=\"3.5\" width=\"6.5\" height=\"6.5\" rx=\"1.5\"/><rect x=\"14\" y=\"3.5\" width=\"6.5\" height=\"6.5\" rx=\"1.5\"/><rect x=\"3.5\" y=\"14\" width=\"6.5\" height=\"6.5\" rx=\"1.5\"/><path d=\"M14 14h2.5v2.5 M20.5 14v.01 M14 20.5h.01 M17.5 18v2.5h3v-3\"/>",
 "coffee": "<path d=\"M4.5 9.5h12v5a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5z M16.5 11h1.5a2.5 2.5 0 0 1 0 5h-1.5 M8.5 3.5v2.5 M12.5 3.5v2.5\"/>",
 "hotspot": "<circle cx=\"12\" cy=\"12\" r=\"1.25\" fill=\"currentColor\" stroke=\"none\"/><path d=\"M8.5 15.5a5 5 0 0 1 0-7 M15.5 8.5a5 5 0 0 1 0 7 M5.6 18.4a9 9 0 0 1 0-12.8 M18.4 5.6a9 9 0 0 1 0 12.8\"/>"
};
