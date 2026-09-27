# Quickshell design and implementation rules

## Intent
Build a personal desktop shell that feels calm, useful, coherent, and carefully made. Human design means judgment: attention goes where the person needs it, details respond predictably, and decoration earns its place. These rules apply to every change in this directory.

## Design direction
- Begin with warm charcoal surfaces, soft off-white text, and one restrained accent. Treat this as an initial direction, adaptable to user feedback and the wallpaper.
- Establish a recognizable identity through typography, proportions, and composition. Avoid generic dashboard styling, rainbow modules, excessive pills, ornamental gradients, and gratuitous glass effects.
- Keep the desktop central. The shell should frame the user's work without competing with it.
- Use three levels of emphasis: primary action or information, supporting status, and quiet metadata. Do not give everything the same visual weight.
- Group related controls with spacing first. Use containers, dividers, and borders only when they make relationships clearer.

## Typography and geometry
- Use one readable interface font with verified local availability and a dependable fallback. Reserve monospace for values that benefit from it.
- Start with a small type scale around 12, 14, and 18 logical pixels; adjust after checking the real display. Never shrink text merely to squeeze in more content.
- Use a spacing scale of 4, 8, 12, 16, 24, and 32 logical pixels. Allow small optical corrections when mechanical alignment looks wrong.
- Centralize colors, spacing, type, radii, and timing in Theme.qml. Prefer one family of modest corner radii over unrelated shapes.
- Align text baselines and balance icon weight with adjacent text. Use one consistent icon family; never emoji as interface icons.
- Keep numbers stable as they update. Long titles must elide gracefully without moving essential controls.

## Color and accessibility
- Color communicates selection, action, or state. Reserve warning and error colors for real warnings and errors.
- Aim for at least 4.5:1 contrast for normal text and 3:1 for large text and meaningful controls. Check actual composited surfaces when using transparency.
- Do not rely on color alone. Provide readable labels or another visible state cue.
- Make pointer targets at least 32 logical pixels where practical, with generous hit areas around compact icons. Provide visible keyboard focus.
- Support keyboard navigation, Escape to dismiss, and sensible focus return in interactive surfaces. Respect reduced motion when available.

## Behavior
- Show only frequently useful information in the bar. Put secondary detail in purposeful popovers.
- Every control must perform a real action and expose appropriate hover, pressed, focused, active, and disabled states.
- Use plain, specific labels and tooltips for ambiguous icons. Avoid clever copy that slows comprehension.
- Design loading, unavailable, empty, error, muted, disconnected, and overflow states alongside the normal state.
- Open popovers close to their trigger, keep them inside the screen, and make dismissal consistent.
- Use subtle motion to explain a state change. Start around 120–180 ms for small transitions; avoid bouncing, pulsing, or continuous decorative animation.
- Never display invented system data or leave a visible placeholder control in the finished interface.

## Engineering
- Keep components small and purposeful. Share tokens and behavior instead of copying magic values.
- Prefer Quickshell services and event-driven updates. Avoid frequent shell polling and unnecessary background processes.
- Verify installed APIs before using them. Handle service loss and absent hardware gracefully.
- Account for multiple monitors, scaling, narrow screens, long text, and changes in system state.
- Preserve a dated backup before destructive resets. Do not overwrite unrelated desktop configuration.
- Implement in useful stages: foundation and bar, essential status and controls, then richer surfaces. Do not build every possible widget by default.

## Review before calling a visual change finished
- Run the shell and inspect logs for QML errors and binding warnings.
- Inspect it on the actual desktop at the user's scale, with both sparse and busy windows behind it. A successful parse alone is not visual validation.
- Check hierarchy, baseline alignment, spacing, contrast, clipping, hit areas, focus, and state transitions.
- Exercise real interactions and at least one unavailable or empty state for affected features.
- Ask whether each visible element helps someone understand or do something. Simplify anything without a clear purpose.
- Report what changed and what was actually checked. State clearly if runtime or visual validation was unavailable.
