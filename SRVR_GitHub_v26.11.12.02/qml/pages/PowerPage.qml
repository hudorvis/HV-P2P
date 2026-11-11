pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"

Item {
    id: page
    objectName: "powerPage"
    required property var powerDevice
    required property var windDevice
    property bool windSelected: false
    readonly property var monitor: windSelected ? windDevice : powerDevice
    readonly property var otherDevice: windSelected ? powerDevice : windDevice
    readonly property string node: windSelected ? "WSI" : "PDM"
    readonly property string unit: windSelected ? "m/s" : "V"
    onVisibleChanged: if (!visible) logSettings.close()
    property real scaleFactor: 1
    readonly property var summary: monitor.summary
    readonly property color cyan: "#26d5ff"
    readonly property color muted: "#aeb4b1"

    function px(size) { return Math.max(1, size * scaleFactor) }

    ColumnLayout {
        anchors.fill: parent
        spacing: page.px(8)

        RowLayout {
            spacing: page.px(6)
            HVButton { text: "PDM"; selected: !page.windSelected; onClicked: page.windSelected = false }
            HVButton { text: "WSI"; selected: page.windSelected; onClicked: page.windSelected = true }
        }

        Panel {
            Layout.fillWidth: true
            implicitHeight: statusRows.implicitHeight + page.px(20)

            ColumnLayout {
                id: statusRows
                anchors.fill: parent
                anchors.margins: page.px(10)
                spacing: page.px(6)

                RowLayout {
                    spacing: page.px(12)
                    Text {
                        text: page.windSelected ? "Wind Speed Indicator" : "Power Distribution Module"
                        color: page.cyan
                        font.pixelSize: page.px(19)
                        font.weight: Font.Medium
                    }
                    Text {
                        text: page.summary.connection
                        color: text === "Live" ? "#63d84e" : text === "Stale data" ? "#e7c94a" : page.muted
                        font.pixelSize: page.px(14)
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: page.node + " address"; color: page.muted; font.pixelSize: page.px(13) }
                    TextField {
                        id: addressField
                        objectName: "pdmAddressField"
                        Layout.preferredWidth: page.px(148)
                        implicitHeight: page.px(30)
                        text: page.monitor.address
                        maximumLength: 15
                        selectByMouse: true
                        color: "#f0f2f1"
                        font.pixelSize: page.px(14)
                        background: Rectangle {
                            color: "#101518"
                            radius: 4
                            border.color: addressField.activeFocus ? page.cyan : "#4a4f52"
                        }
                        onAccepted: applyAddress.clicked()
                    }
                    HVButton {
                        id: applyAddress
                        text: "Apply"
                        implicitHeight: page.px(30)
                        implicitWidth: page.px(72)
                        font.pixelSize: page.px(14)
                        onClicked: {
                            const address = addressField.text.trim()
                            addressError.text = address && address === page.otherDevice.address
                                ? "Enter a separate address for each device"
                                : page.monitor.saveAddress(address)
                        }
                    }
                    HVButton {
                        objectName: "monitorLogButton"
                        text: "Log Settings"
                        implicitHeight: page.px(30)
                        implicitWidth: page.px(112)
                        font.pixelSize: page.px(14)
                        enabled: page.summary.online && !page.monitor.logBusy
                        onClicked: logSettings.open()
                    }
                    HVButton {
                        text: "Open " + page.node + " Web UI"
                        enabled: page.monitor.address.length > 0
                        implicitHeight: page.px(30)
                        implicitWidth: page.px(178)
                        font.pixelSize: page.px(14)
                        onClicked: page.monitor.openWeb()
                    }
                }

                RowLayout {
                    spacing: page.px(12)
                    Text {
                        text: "Firmware " + page.summary.version + "  •  " + page.summary.update
                        textFormat: Text.PlainText
                        color: page.muted
                        font.pixelSize: page.px(13)
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    ProgressBar {
                        visible: page.summary.online && page.summary.progress > 0
                        value: Math.min(100, Math.max(0, page.summary.progress)) / 100
                        Layout.preferredWidth: page.px(110)
                    }
                    Text {
                        visible: page.summary.online && page.summary.progress > 0
                        text: page.summary.progress + "%"
                        color: page.cyan
                        font.pixelSize: page.px(13)
                    }
                    Text {
                        text: page.summary.when
                            ? "Last sample " + Qt.formatDateTime(new Date(page.summary.when), "dd MMM hh:mm:ss")
                              + (page.summary.estimated ? " (estimated)" : "")
                            : "Waiting for samples"
                        color: page.muted
                        font.pixelSize: page.px(13)
                    }
                }
                Text {
                    id: addressError
                    Layout.fillWidth: true
                    visible: text.length > 0
                    color: "#ef5757"
                    font.pixelSize: page.px(13)
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: page.monitor.bundleNote
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: "#e7c94a"
                    font.pixelSize: page.px(13)
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: page.windSelected ? 1 : 2
            columnSpacing: page.px(8)
            rowSpacing: page.px(8)

            Repeater {
                model: page.windSelected ? 1 : 4

                Panel {
                    id: channel
                    required property int index
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 1
                    readonly property var volts: page.summary.voltages[index]
                    readonly property string alarm: page.summary.alarms[index] || ""

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: page.px(12)
                        spacing: page.px(4)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: page.px(8)
                            Text {
                                Layout.fillWidth: true
                                text: page.summary.labels[channel.index] || ""
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: page.cyan
                                font.pixelSize: page.px(18)
                                font.weight: Font.Medium
                            }
                            Text {
                                text: channel.alarm
                                textFormat: Text.PlainText
                                visible: (text === "LOW" || text === "HIGH") && page.summary.connection === "Live"
                                color: "#e7c94a"
                                font.pixelSize: page.px(13)
                            }
                            Text {
                                text: channel.volts === null || channel.volts === undefined || page.summary.connection !== "Live"
                                      ? "— " + page.unit : Number(channel.volts).toFixed(2) + " " + page.unit
                                color: "#f0f2f1"
                                font.pixelSize: page.px(21)
                                font.weight: Font.Medium
                            }
                        }

                        PowerTrace {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            points: page.monitor.graphs[channel.index] || []
                            scaleFactor: page.scaleFactor
                            traceColor: page.cyan
                            unit: page.unit
                        }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: page.summary.history + "  •  " + page.summary.hours + " h  •  "
                  + page.summary.samples.toLocaleString(Qt.locale(), "f", 0) + " samples"
                  + (page.summary.online ? ("  •  " + page.node + (page.summary.logging ? " logging" : " logging unavailable")) : "")
            color: page.muted
            font.pixelSize: page.px(13)
        }
    }

    Connections {
        target: page.monitor
        function onLogSettingsFinished(ok, hours, period, error) {
            if (!logSettings.visible)
                return
            if (!ok) {
                logError.text = error
                return
            }
            if (logSettings.saving) {
                logSettings.close()
                return
            }
            duration.currentIndex = hours - 1
            interval.currentIndex = logSettings.periods.indexOf(period)
            logSettings.loaded = true
        }
    }

    Dialog {
        id: logSettings
        objectName: "monitorLogSettings"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: page.px(380)
        padding: page.px(16)
        modal: true
        closePolicy: Popup.NoAutoClose
        property bool loaded: false
        property bool saving: false
        readonly property var periods: [250, 500, 1000, 2000]
        background: Panel {}
        onOpened: {
            loaded = false
            saving = false
            logError.text = ""
            if (!page.monitor.loadLogSettings())
                logError.text = "Unable to read settings"
        }
        contentItem: ColumnLayout {
            spacing: page.px(10)
            Text {
                text: page.node + " Log Settings"
                color: page.cyan
                font.pixelSize: page.px(19)
            }
            RowLayout {
                enabled: logSettings.loaded && !page.monitor.logBusy
                Text { Layout.fillWidth: true; text: "Log Interval"; color: page.muted }
                ComboBox { id: interval; objectName: "monitorLogInterval"; Layout.preferredWidth: page.px(120); model: ["0.25 s", "0.5 s", "1.0 s", "2.0 s"] }
            }
            RowLayout {
                enabled: logSettings.loaded && !page.monitor.logBusy
                Text { Layout.fillWidth: true; text: "Log Duration"; color: page.muted }
                ComboBox {
                    id: duration
                    objectName: "monitorLogDuration"
                    Layout.preferredWidth: page.px(120)
                    model: Array.from({length: 12}, (_, i) => (i + 1) + " h")
                }
            }
            Text {
                id: logError
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                color: "#ef5757"
                visible: text.length > 0
            }
            Text {
                text: logSettings.saving ? "Saving settings…" : "Reading settings…"
                visible: page.monitor.logBusy
                color: page.muted
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HVButton { text: "Cancel"; enabled: !page.monitor.logBusy; onClicked: logSettings.close() }
                HVButton {
                    objectName: "monitorLogApply"
                    text: "Apply"
                    enabled: logSettings.loaded && !page.monitor.logBusy
                    onClicked: {
                        logError.text = ""
                        logSettings.saving = page.monitor.saveLogSettings(duration.currentIndex + 1,
                            logSettings.periods[interval.currentIndex])
                        if (!logSettings.saving)
                            logError.text = "Unable to save settings"
                    }
                }
            }
        }
    }
}
