pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "GetApps.js" as GetAppsLogic

// Get apps inside the launcher (Super + Shift + A): the page router.
//   choose    the chooser: where should the app come from?     ChooserPage
//   flatpak   Flathub apps · dnf  Fedora packages               SourcePage
//   web       Web apps (arctic-webapp, only when installed)     WebAppPage
//   terminal  Terminal apps: a terminal program in the launcher TerminalAppPage
//   remove    Remove apps, with a tab per source                RemovePage
//   console   the dnf / flatpak console                         ConsolePage
// Esc goes back one step and never closes the launcher from here: a sheet closes, then the
// field clears, then the chooser, then the launcher home (GetApps.js backStep). The work itself
// belongs to AppsService, so leaving a page never stops an install.
FocusScope {
    id: router
    property string page: 'choose'
    property string removeTab: ''                 // remove/<tab>, or dnf/all|apps
    property string query: ''
    readonly property Item inputItem: loader.item && loader.item.inputItem ? loader.item.inputItem : router
    readonly property int preferredWidth: page === 'choose' ? 640 : 760
    readonly property int preferredHeight: page === 'choose' && loader.item ? Math.round(loader.item.implicitHeight) + 2 * Theme.space3 : 600
    signal backRequested()
    signal closeRequested()

    function open(target, text) {
        const parsed = GetAppsLogic.parsePage(target);
        let next = parsed.page;
        if (next === 'remove' && Session.live) next = 'choose';
        if (next === 'web' && AppsService.sourcesLoaded && !AppsService.webappPresent) next = 'choose';
        AppsService.ensureStarted();
        query = text || '';
        removeTab = parsed.tab;
        if (next === page && loader.item) {
            if (loader.item.reopen) loader.item.reopen(query, removeTab);
        } else {
            page = next;
        }
        Qt.callLater(focusPage);
    }
    function focusPage() { if (inputItem) inputItem.forceActiveFocus(); }
    function back() {
        if (loader.item && loader.item.back && loader.item.back()) return;
        if (page !== 'choose') open('choose', '');
        else backRequested();
    }

    focus: true
    Keys.onEscapePressed: event => { router.back(); event.accepted = true; }

    Loader {
        id: loader
        anchors.fill: parent
        focus: true
        sourceComponent: router.page === 'flatpak' || router.page === 'dnf' ? sourcePage
                         : router.page === 'nix' ? nixPage
                         : router.page === 'remove' ? removePage
                         : router.page === 'console' ? consolePage
                         : router.page === 'web' ? webPage
                         : router.page === 'terminal' ? terminalPage
                         : chooser
        onLoaded: Qt.callLater(router.focusPage)
    }
    Component {
        id: chooser
        ChooserPage {
            onOpenPage: name => router.open(name, '')
            onBackRequested: router.backRequested()
        }
    }
    Component {
        id: sourcePage
        SourcePage {
            source: router.page
            initialQuery: router.query
            initialView: router.removeTab
            onBackRequested: router.open('choose', '')
            onOpenPage: (name, text) => router.open(name, text)
            onCloseRequested: router.closeRequested()
        }
    }
    Component {
        id: nixPage
        NixPage { initialQuery: router.query; onBackRequested: router.open('choose', '') }
    }
    Component {
        id: removePage
        RemovePage {
            initialTab: router.removeTab
            initialFilter: router.query
            onOpenPage: name => router.open(name, '')
            onBackRequested: router.open('choose', '')
        }
    }
    Component {
        id: consolePage
        ConsolePage {
            Component.onCompleted: open()
            onBackRequested: router.open('choose', '')
        }
    }
    Component {
        id: webPage
        WebAppPage {
            initialQuery: router.query
            onBackRequested: router.open('choose', '')
            onCloseRequested: router.closeRequested()
        }
    }
    Component {
        id: terminalPage
        TerminalAppPage {
            onBackRequested: router.open('choose', '')
            onOpenPage: (name, text) => router.open(name, text)
        }
    }
}

