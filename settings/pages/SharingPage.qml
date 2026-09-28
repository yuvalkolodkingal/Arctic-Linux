// Sharing: what other computers and phones on the network may reach. The firewall (firewalld,
// its default zone) is read as the user; letting something through and remote login (sshd, and
// whether it takes passwords) change through Settings' root helper (pkexec
// arctic-system-helper, one password for a few minutes). Remote login is hidden in the live
// session.
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Sharing"
    lede: "What other computers and phones on your network can reach on this one."
    property var info: ({ firewall: { installed: true, running: false }, allows: {}, installed: {}, ssh: { installed: false }, live: false })
    property bool busy: false
    function load() {
        Backend.call(["sharing"], r => { if (r.ok) page.info = r; });
    }
    function change(args, message) {
        page.busy = true;
        Backend.call(["sharing-set"].concat(args), r => {
            page.busy = false;
            if (r.ok) {
                page.info = r;
                Backend.notify("success", message, false);
            } else {
                page.load();
            }
        });
    }
    onShown: load()

    Group {
        title: "This computer"
        SettingRow {
            searchKey: "sharing.firewall"
            title: "Firewall"
            desc: {
                const f = page.info.firewall || {};
                if (!f.installed)
                    return "No firewall is installed (sudo dnf install firewalld).";
                if (!f.running)
                    return "The firewall is off: anything on the network can reach the services running here.";
                return "On. It lets in only what’s allowed below" + (f.zone ? " (zone " + f.zone + ")" : "") + ".";
            }
            resettable: false
            ArButton {
                visible: page.info.installed && page.info.installed.firewallConfig === true
                text: "Firewall settings"
                iconRight: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["firewall-config"])
            }
        }
        SettingRow {
            visible: !!page.info.hostname
            title: "Name on the network"
            desc: (page.info.avahi ? "Other computers find it as " + page.info.mdnsName + "." : "Other computers see it as " + page.info.hostname + ".") + " Change it in About."
            resettable: false
        }
    }

    Group {
        visible: page.info.firewall && page.info.firewall.running === true
        title: "Let in"
        desc: "Each asks for your password and lasts until you switch it off."
        SettingRow {
            searchKey: "sharing.mdns"
            title: "Find printers and devices on the network"
            desc: "Answers when printers, speakers and other computers look for each other (mDNS)."
            resettable: false
            RowSwitch {
                Accessible.name: "Find printers and devices on the network"
                enabled: !page.busy
                checked: page.info.allows.mdns === true
                onToggled: page.change(["allow", "mdns", checked ? "on" : "off"], checked ? "mDNS is let in" : "mDNS is blocked")
            }
        }
        SettingRow {
            visible: page.info.installed.localsend === true
            searchKey: "sharing.localsend"
            title: "LocalSend"
            desc: "Receive files from phones and computers nearby (port 53317)."
            resettable: false
            RowSwitch {
                Accessible.name: "Let LocalSend receive files"
                enabled: !page.busy
                checked: page.info.allows.localsend === true
                onToggled: page.change(["allow", "localsend", checked ? "on" : "off"], checked ? "LocalSend is let in" : "LocalSend is blocked")
            }
        }
        SettingRow {
            visible: page.info.installed.kdeconnect === true
            searchKey: "sharing.kdeconnect"
            title: "KDE Connect"
            desc: "Your phone can reach this computer: files, notifications, the clipboard."
            resettable: false
            RowSwitch {
                Accessible.name: "Let KDE Connect reach this computer"
                enabled: !page.busy
                checked: page.info.allows.kdeconnect === true
                onToggled: page.change(["allow", "kdeconnect", checked ? "on" : "off"], checked ? "KDE Connect is let in" : "KDE Connect is blocked")
            }
        }
    }

    ArBanner {
        visible: page.info.live !== true && page.info.ssh.enabled === true && page.info.ssh.passwordLogin === false && page.info.ssh.authorizedKeys === false
        width: parent.width
        kind: "warning"
        text: "Nobody can log in remotely yet: add a public key to ~/.ssh/authorized_keys, or allow password login."
    }
    Group {
        visible: page.info.live !== true && page.info.ssh.installed === true
        title: "Remote login"
        SettingRow {
            searchKey: "sharing.ssh"
            title: "Remote login (SSH)"
            desc: page.info.ssh.enabled ? "On. Connect with: ssh " + (page.info.ssh.user || "you") + "@" + (page.info.mdnsName || page.info.hostname || "this-computer")
                    + (page.info.ssh.fingerprint ? " (key " + page.info.ssh.fingerprint + ")" : "")
                : "Off. Turn it on to log in to this computer from another one."
            resettable: false
            RowSwitch {
                Accessible.name: "Remote login"
                enabled: !page.busy
                checked: page.info.ssh.enabled === true
                onToggled: page.change(["ssh", checked ? "on" : "off"], checked ? "Remote login is on" : "Remote login is off")
            }
        }
        SettingRow {
            visible: page.info.ssh.enabled === true
            searchKey: "sharing.password"
            title: "Allow password login"
            desc: "Off means only the keys in ~/.ssh/authorized_keys can log in, which is safer."
            resettable: false
            RowSwitch {
                Accessible.name: "Allow password login"
                enabled: !page.busy
                checked: page.info.ssh.passwordLogin === true
                onToggled: page.change(["ssh-password", checked ? "on" : "off"], checked ? "Passwords are allowed" : "Keys only")
            }
        }
    }
}
