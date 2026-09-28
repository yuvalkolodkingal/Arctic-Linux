pragma Singleton
import QtQuick
import Quickshell

// Shared by every menu row: whether the last input was a key (focus rings and the keyboard
// highlight show) or the pointer (only hover highlights). Only one bar menu is open at a time.
Singleton {
    property bool keyboardNav: false
}
