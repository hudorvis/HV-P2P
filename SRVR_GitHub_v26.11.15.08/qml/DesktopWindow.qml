import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: desktop
    visible: true
    width: 1672
    height: 941
    minimumWidth: 1280
    minimumHeight: 720
    title: "HV P2P SRVR v" + appVersion
    color: view.bg
    font.family: "Helvetica Neue"

    property var webShare: null
    readonly property QtObject navigation: navigationState
    property alias page: navigationState.page
    property alias shortcutTab: navigationState.shortcutTab

    SrvrNavigation { id: navigationState }
    Main {
        id: view
        anchors.fill: parent
        navigation: navigationState
        webShare: desktop.webShare
    }
}
