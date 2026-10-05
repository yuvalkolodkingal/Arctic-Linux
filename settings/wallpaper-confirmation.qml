// Preview the actual public-wallpaper confirmation without making a system change.
import QtQuick
import Quickshell
import "pages" as Pages
ShellRoot {
    FloatingWindow {
        visible: true
        implicitWidth: 960
        implicitHeight: 700
        color: "#12171e"
        title: "Arctic wallpaper confirmation preview"
        Pages.AppearancePage {
            id: page
            anchors.fill: parent
            Component.onCompleted: confirm.start()
        }
        Timer {
            id: confirm
            interval: 1000
            onTriggered: page.requestLoginWallpaper("sync-desktop", "")
        }
    }
}
