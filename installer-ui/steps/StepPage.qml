// Base for every wizard page. shell.qml draws the rail, the header (overline,
// title, lede — or the aurora hero on Welcome/Done) and the footer from these
// properties; the page itself only lays out its one decision.
import QtQuick
import ".."

FocusScope {
    id: page
    property string stepId: ""
    property string overline: ""          // default "Step n of 10"
    property string title: Wizard.step.title || ""
    property string lede: ""
    property string hero: ""              // "welcome" | "done": big title + aurora band
    property string note: ""              // footer reassurance, bottom-left
    property string caption: ""           // footer text when there are no buttons
    property bool showBack: true
    property bool showNext: true
    property string nextLabel: "Next"
    property string nextIcon: ""          // leading icon on the primary button
    property string secondaryLabel: ""    // ghost button before the primary (Done: Keep trying)
    property bool valid: true
    property bool fade: false             // soft fade above the footer (scrolling content)
    property bool fillHeight: false       // page takes all remaining height
    property int measure: 560             // max content width (bundle: 480–640)
    property real availableHeight: 400    // set by the frame
    property string helpText: ""          // F1 help
    property bool keyboardUsed: true
    // The primary action only works this long after the page appeared: a double click or
    // a key press meant for the previous page must not land on this one.
    property int armDelay: 400
    property bool armVisible: false       // show the primary button disabled until then
    // Enter anywhere on the page presses the primary action (Summary: only the button).
    property bool enterActivates: true

    // Save this step (SetSecrets / SetStep). Call done(true) to continue.
    function commit(done) {
        done(true);
    }
    // Primary footer action. Default: commit, then Next. `committing` keeps a second
    // press out until Next has answered (Wizard.next() then holds `busy`).
    function primary() {
        Wizard.committing = true;
        commit(ok => {
            if (ok)
                Wizard.next();
            else
                Wizard.committing = false;
        });
    }
    function secondary() {
    }
    // Test hook (IPC "fill"): set form values from an object.
    function fillForm(values) {
        return "not supported on this step";
    }
    // Put keyboard focus on the page's main control.
    function focusFirst() {
    }

    width: measure
    implicitHeight: childrenRect.height
}
