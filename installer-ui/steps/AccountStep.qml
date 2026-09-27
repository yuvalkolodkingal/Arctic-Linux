// Step 7 — Create your account (INSTALL_STEPS[6]). Your name → username
// (auto-filled, lowercase, editable) → password + confirm → computer name
// ({username}-{model}, suggested by the engine). Passwords go to SetSecrets only.
import QtQuick
import ".."
import "../components"

StepPage {
    id: page
    stepId: "account"
    title: "Create your account"
    lede: ""
    measure: 560
    note: showFixNote ? "Fix the highlighted field to continue." : ""
    valid: fullName.text.trim() !== "" && username.text !== "" && hostname.text !== "" && password.text !== "" && password.text === confirm.text && strength.score >= 1 && localUsernameError === "" && Object.keys(Wizard.fieldErrors).length === 0
    helpText: "This is the account you log in with. Your username is filled in from your name; you can change it. The computer name is how other devices on your network see this computer."

    readonly property var d: Wizard.step.data || {}
    readonly property var opts: Wizard.step.options || {}
    property bool usernameTouched: (d.username || "") !== ""
    property bool hostnameTouched: false
    property bool sameAsDisk: false
    property bool autologin: !!d.autologin
    property var strength: ({
            score: 0,
            label: "",
            words: 0,
            ok: false
        })
    readonly property string localUsernameError: username.text !== "" && !/^[a-z_][a-z0-9_-]*$/.test(username.text) ? "Use lowercase letters, numbers, - and _." : ""
    readonly property bool mismatch: confirm.text !== "" && confirm.text !== password.text
    readonly property bool showFixNote: mismatch || localUsernameError !== "" || Object.keys(Wizard.fieldErrors).length > 0

    function suggest() {
        const name = fullName.text.trim();
        if (name === "")
            return;
        Engine.call("SuggestAccount", {
            full_name: name
        }, (res, err) => {
            if (err || fullName.text.trim() !== name)
                return;
            if (!usernameTouched)
                username.text = res.username || "";
            if (!hostnameTouched)
                hostname.text = res.hostname || "";
        });
    }
    function check() {
        const t = password.text;
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
            if (!err && password.text === t)
                strength = res;
        });
    }
    function commit(done) {
        const secrets = {
            user_password: password.text
        };
        if (sameAsDisk && Wizard.encryptionEnabled)
            secrets.luks_passphrase = password.text;
        Engine.call("SetSecrets", secrets, (res, err) => {
            if (err) {
                Wizard.showError(err);
                done(false);
                return;
            }
            Wizard.saveStep("account", {
                full_name: fullName.text.trim(),
                username: username.text,
                hostname: hostname.text,
                autologin: autologin
            }, done);
        });
    }
    function focusFirst() {
        fullName.forceActiveFocus();
    }
    function fillForm(v) {
        // behave like typing: a changed field drops its engine error
        for (const k of ["full_name", "username", "hostname", "password"])
            if (v[k] !== undefined)
                Wizard.clearFieldError(k);
        if (v.full_name !== undefined) {
            fullName.text = v.full_name;
            suggestTimer.restart();
        }
        if (v.username !== undefined) {
            username.text = v.username;
            usernameTouched = true;
        }
        if (v.hostname !== undefined) {
            hostname.text = v.hostname;
            hostnameTouched = true;
        }
        if (v.password !== undefined)
            password.text = v.password;
        if (v.confirm !== undefined)
            confirm.text = v.confirm;
        if (v.same_as_disk !== undefined)
            sameAsDisk = !!v.same_as_disk;
        if (v.autologin !== undefined)
            autologin = !!v.autologin;
        check();
        if (v.focus === "confirm")
            confirm.forceActiveFocus();
        return "ok";
    }

    Component.onCompleted: {
        fullName.text = d.full_name || "";
        username.text = d.username || "";
        hostname.text = d.hostname || "";
    }

    Timer {
        id: suggestTimer
        interval: 200
        onTriggered: page.suggest()
    }
    Timer {
        id: checkTimer
        interval: 150
        onTriggered: page.check()
    }

    Grid {
        id: grid
        width: page.width
        columns: 2
        columnSpacing: Theme.space4
        rowSpacing: Theme.space4
        readonly property real colWidth: (width - columnSpacing) / 2

        ArInput {
            id: fullName
            width: grid.colWidth
            label: "Your name"
            error: Wizard.fieldErrors.full_name || ""
            onEdited: {
                Wizard.clearFieldError("full_name");
                suggestTimer.restart();
            }
        }
        ArInput {
            id: username
            width: grid.colWidth
            label: "Username"
            help: page.usernameTouched ? "Lowercase letters, numbers, - and _." : "Filled in from your name."
            error: Wizard.fieldErrors.username || page.localUsernameError
            onEdited: {
                Wizard.clearFieldError("username");
                page.usernameTouched = true;
                const lower = text.toLowerCase();
                if (lower !== text)
                    text = lower;
            }
        }
        ArInput {
            id: password
            width: grid.colWidth
            label: "Password"
            password: true
            meterLevel: text === "" ? 0 : page.strength.score
            meterLabel: page.strength.label
            help: text === "" ? "" : page.strength.label
            error: Wizard.fieldErrors.password || ""
            onEdited: {
                Wizard.clearFieldError("password");
                checkTimer.restart();
            }
        }
        ArInput {
            id: confirm
            width: grid.colWidth
            label: "Confirm password"
            password: true
            error: page.mismatch ? "Passwords don’t match yet." : ""
            success: confirm.text !== "" && !page.mismatch ? "Matches" : ""
            trailingIcon: confirm.text !== "" && !page.mismatch ? "check" : ""
        }
    }

    Column {
        anchors.top: grid.bottom
        anchors.topMargin: Theme.space4
        width: page.width
        spacing: Theme.space4

        ArInput {
            id: hostname
            width: parent.width
            label: "Computer name"
            iconName: "cpu"
            help: (page.opts.hostname_hint || "Suggested from your name and computer") + ". This is how other devices see it."
            error: Wizard.fieldErrors.hostname || ""
            onEdited: {
                Wizard.clearFieldError("hostname");
                page.hostnameTouched = true;
                const lower = text.toLowerCase();
                if (lower !== text)
                    text = lower;
            }
        }
        ArToggle {
            visible: Wizard.encryptionEnabled
            text: "Use this password for the disk passphrase too"
            checked: page.sameAsDisk
            onToggled: page.sameAsDisk = checked
        }
        ArToggle {
            text: "Log in automatically"
            checked: page.autologin
            onToggled: page.autologin = checked
        }
    }
}
