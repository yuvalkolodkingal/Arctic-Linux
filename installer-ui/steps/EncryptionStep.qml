// Step 6 — Create an encryption passphrase (INSTALL_STEPS[5]). Strength meter
// from the engine (CheckPassphrase), Next from "Fair" upward and when both match.
// The passphrase only ever goes to SetSecrets.
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "encryption"
    title: "Create an encryption passphrase"
    lede: "You’ll type this each time the computer starts, before logging in."
    measure: 480
    valid: !enabled_ || (strength.ok === true && matches)
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
        Engine.call("SetSecrets", {
            luks_passphrase: enabled_ ? pass.text : ""
        }, (res, err) => {
            if (err) {
                Wizard.showError(err);
                done(false);
                return;
            }
            Wizard.saveStep("encryption", {
                enabled: enabled_
            }, done);
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
            error: Wizard.fieldErrors.passphrase || ""
            help: text === "" ? "Longer is stronger — a short sentence works well." : (page.strength.label ? page.strength.label + " · " + page.strength.words + (page.strength.words === 1 ? " word" : " words") + ". Longer is stronger — a short sentence works well." : "")
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
