// Preview the actual public-wallpaper confirmation without making a system change.
import QtQuick
import QtQuick.Window
import ".." 1.0
Window {
    visible: true
    width: 960
    height: 700
    color: Theme.ground
    title: "Arctic wallpaper confirmation preview"
    Loader {
        anchors.fill: parent
        source: "../pages/AppearancePage.qml"
        onLoaded: Qt.callLater(() => item.requestLoginWallpaper("sync-desktop", ""))
    }
}
