import QtQuick

// "Restart to update" on the bar while updates wait for the next restart (UpdateService): the
// accent pill with the download icon. The bar opens the updates popover on click.
BarItem {
    visible: UpdateService.ready
    accentFill: true
    iconName: 'download'
    iconColor: Theme.onAccent
    text: 'Restart to update'
    textColor: Theme.onAccent
    textWeight: Font.DemiBold
    tooltip: 'Updates ready · ' + UpdateService.summary + ' · installed when you restart'
}
