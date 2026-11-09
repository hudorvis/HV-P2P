pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"

Item {
    // Read-only instrument view. Device configuration stays in the web UI.
    id: page
    objectName: "powerPage"
    required property var monitor
    property real scaleFactor: 1
    readonly property var summary: monitor.summary
    readonly property color cyan: "#26d5ff"
    readonly property color muted: "#aeb4b1"

    function px(size) { return Math.max(1, size * scaleFactor) }

    ColumnLayout {
        anchors.fill: parent
        spacing: page.px(8)

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
                        text: "Power Distribution Monitor"
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
                    Text { text: "PDM address"; color: page.muted; font.pixelSize: page.px(13) }
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
                        onClicked: addressError.text = page.monitor.saveAddress(addressField.text)
                    }
                    HVButton {
                        text: "Open PDM Web UI"
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
            columns: 2
            columnSpacing: page.px(8)
            rowSpacing: page.px(8)

            Repeater {
                model: 4

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
                                text: page.summary.labels[channel.index]
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
                                      ? "— V" : Number(channel.volts).toFixed(2) + " V"
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
                        }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: page.summary.history + "  •  " + page.summary.hours + " h  •  "
                  + page.summary.samples.toLocaleString(Qt.locale(), "f", 0) + " samples"
                  + (page.summary.online ? (page.summary.logging ? "  •  PDM logging" : "  •  PDM logging unavailable") : "")
            color: page.muted
            font.pixelSize: page.px(13)
        }
    }
}
