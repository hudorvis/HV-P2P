import QtQuick

Item {
    id: viewport
    required property SrvrNavigation navigation
    required property var webShare
    property real layoutWidth: 1280
    // Browser zoom and DPR can change the raster density independently of the
    // usable CSS area. Share the desktop layout at the CSS geometry.
    readonly property real sceneScale: layoutWidth / Math.max(1, width)

    Main {
        objectName: "webSrvrView"
        width: viewport.layoutWidth
        height: viewport.height * viewport.sceneScale
        scale: 1 / viewport.sceneScale
        transformOrigin: Item.TopLeft
        navigation: viewport.navigation
        webShare: viewport.webShare
        tracksMonitorHistory: false
    }
}
