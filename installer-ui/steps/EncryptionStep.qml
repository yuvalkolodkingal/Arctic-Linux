// Step 6 — Create an encryption passphrase (INSTALL_STEPS[5]). Strength meter
// from the engine (CheckPassphrase); Next once both fields match. Below "Fair"
// (options.min_score) a warning banner says it is easy to guess, but any passphrase
// is accepted. The passphrase only ever goes to SetSecrets. Coming back (Summary
// "Change"), the engine still has it (options.passphrase_set): empty fields keep it.
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "encryption"
    title: "Create an encryption passphrase"
    lede: "You’ll type this each time the computer starts, before logging in."
    measure: 480
    valid: !enabled_ || keep || (matches && latinError === "")
    helpText: "The passphrase protects everything on the disk. You’ll type it each time the computer starts. A few random words are easy to remember and hard to guess — try Suggest a passphrase."

    property bool enabled_: Wizard.step.data && Wizard.step.data.enabled !== undefined ? !!Wizard.step.data.enabled : true
    property var strength: ({
            score: 0,
            label: "",
            words: 0,
            ok: false
        })
    readonly property bool matches: pass.text !== "" && pass.text === confirm.text
    readonly property bool mismatch: confirm.text !== "" && pass.text !== confirm.text
    readonly property bool saved: !!(Wizard.step.options && Wizard.step.options.passphrase_set)
    readonly property bool keep: enabled_ && saved && pass.text === "" && confirm.text === ""
    readonly property var opts: Wizard.step.options || {}
    readonly property int minScore: opts.min_score !== undefined ? opts.min_score : 2
    // Easy to guess: a warning, never a reason to keep Next off. For the typed passphrase
    // once the engine has scored it; for a kept one from options.strength.
    readonly property bool weak: enabled_ && (keep ? !!opts.strength && opts.strength.score < minScore : pass.text !== "" && strength.label !== "" && strength.score < minScore)
    // For tests (IPC state().step).
    testState: ({
            weak: weak,
            label: strength.label
        })
    // The passphrase is asked for when the computer starts, where a layout that can't type
    // Latin letters isn't available (the engine installs English (US) there): only
    // characters typed with English (US) work.
    readonly property string latinError: Wizard.keyboardNonLatin && /[^\x20-\x7e]/.test(pass.text) ? "Use English (US) letters, numbers and symbols: the computer asks for it before your layout is loaded." : ""

    function check() {
        const t = pass.text;
        if (t === "") {
            strength = {
                score: 0,
                label: "",
                words: 0,
                ok: false
            };
            return;
        }
        Engine.call("CheckPassphrase", {
            text: t
        }, (res, err) => {
            if (!err && pass.text === t)
                strength = res;
        });
    }
    function suggest() {
        Engine.call("SuggestPassphrase", null, (res, err) => {
            if (err)
                return;
            pass.revealed = true;
            confirm.revealed = true;
            pass.text = res.text;
            confirm.text = res.text;
            check();
        });
    }
    function commit(done) {
        const save = () => Wizard.saveStep("encryption", {
                enabled: enabled_
            }, done);
        if (keep) {
            save();
            return;
        }
        Engine.call("SetSecrets", {
            luks_passphrase: enabled_ ? pass.text : ""
        }, (res, err) => {
            if (err) {
                Wizard.showError(err);
                done(false);
                return;
            }
            save();
        });
    }
    function focusFirst() {
        if (enabled_)
            pass.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.enabled !== undefined)
            enabled_ = !!v.enabled;
        if (v.passphrase !== undefined) {
            Wizard.clearFieldError("passphrase");
            pass.text = v.passphrase;
        }
        if (v.confirm !== undefined)
            confirm.text = v.confirm;
        if (v.reveal !== undefined) {
            pass.revealed = !!v.reveal;
            confirm.revealed = !!v.reveal;
        }
        if (v.suggest)
            suggest();
        check();
        if (v.focus === "confirm")
            confirm.forceActiveFocus();
        return "ok";
    }

    Timer {
        id: checkTimer
        interval: 150
        onTriggered: page.check()
    }

    Column {
        width: page.width
        spacing: Theme.space4

        ArInput {
            id: pass
            visible: page.enabled_
            width: parent.width
            label: "Passphrase"
            password: true
            meterLevel: text === "" ? 0 : page.strength.score
            meterLabel: page.strength.label
            error: Wizard.fieldErrors.passphrase || page.latinError
            help: text === "" ? (page.saved ? "Your passphrase is saved. Leave this empty to keep it, or type a new one." : "Longer is stronger — a short sentence works well.") : (page.strength.label ? page.strength.label + " · " + page.strength.words + (page.strength.words === 1 ? " word" : " words") + ". Longer is stronger — a short sentence works well." : "")
            onEdited: {
                Wizard.clearFieldError("passphrase");
                checkTimer.restart();
            }
        }

        ArInput {
            id: confirm
            visible: page.enabled_
            width: parent.width
            label: "Type it again"
            password: true
            error: page.mismatch ? "Passphrases don’t match yet." : ""
            success: page.matches ? "Matches" : ""
            trailingIcon: page.matches ? "check" : ""
        }

        Row {
            visible: page.enabled_
            spacing: Theme.space2
            ArButton {
                variant: "ghost"
                iconName: "sparkle"
                text: "Suggest a passphrase"
                onClicked: page.suggest()
            }
        }

        ArBanner {
            visible: page.weak
            width: parent.width
            kind: "warning"
            text: page.opts.weak_warning || "This passphrase is easy to guess: someone who has your computer could read your files. You can still use it."
        }

        ArBanner {
            visible: page.enabled_ && Wizard.keyboardNonLatin
            width: parent.width
            kind: "info"
            text: "Type it with the English (US) layout. When the computer starts, it asks for the passphrase in English (US)."
        }

        ArBanner {
            width: parent.width
            kind: "warning"
            strong: true
            text: page.enabled_ ? "If you forget this passphrase, <b>no one can recover your files</b> — not even us. Write it down somewhere safe." : "Without encryption, <b>anyone who has this computer can read your files</b>, even without your password."
        }

        ArToggle {
            text: "Encrypt the disk (recommended)"
            checked: page.enabled_
            onToggled: page.enabled_ = checked
        }
    }
}
