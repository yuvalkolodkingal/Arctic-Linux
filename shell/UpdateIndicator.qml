import QtQuick

// The bar's update item (UpdateService), the accent pill. Updates are installed while the
// computer runs, so it only shows when something is left for you: "Restart when you like" after
// an update that only a restart loads (a kernel, a driver, firmware), or "Restart to update"
// when updates were stored for the next restart. The bar opens the updates popover on click.
BarItem {
    visible: UpdateService.attention
    accentFill: true
    iconName: UpdateService.ready ? 'download' : 'restart'
    iconColor: Theme.onAccent
    text: UpdateService.ready ? 'Restart to update' : 'Restart when you like'
    textColor: Theme.onAccent
    textWeight: Font.DemiBold
    tooltip: UpdateService.ready
        ? 'Updates ready · ' + UpdateService.summary + ' · installed when you restart'
        : 'Updates are installed · a restart starts using the new kernel, driver or firmware'
}
