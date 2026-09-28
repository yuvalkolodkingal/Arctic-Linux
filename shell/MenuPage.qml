import QtQuick

// A page inside a bar menu (a network's actions, the pairing list, a Quick Settings panel): a
// back row ("‹ Wi-Fi") and a title over a MenuList. Left, Backspace and Esc go back.
MenuList {
    id: page
    property string title: ''
    property string detail: ''
    property string backText: 'Back'
    isPage: true

    MenuHeader {
        title: page.title
        detail: page.detail
        backText: page.backText
        onBack: page.back()
    }
}
