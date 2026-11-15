import QtQuick

Item {
    id: viewport
    required property SrvrNavigation navigation
    required property var webShare
    property real pixelDensity: 1
    // Match the browser's proportions without squeezing the desktop layout
    // below its design metrics when the backing image is small or ultrawide.
    readonly property real sceneScale: Math.min(4096 / Math.max(1, width, height),
                                                Math.max(pixelDensity, 1672 / Math.max(1, width),
                                                         941 / Math.max(1, height)))

    Main {
        objectName: "webSrvrView"
        width: viewport.width * viewport.sceneScale
        height: viewport.height * viewport.sceneScale
        scale: 1 / viewport.sceneScale
        transformOrigin: Item.TopLeft
        navigation: viewport.navigation
        webShare: viewport.webShare
        tracksMonitorHistory: false
    }
}
