# HV P2P SYS v26.11.12.03

**Monitoring → PDM** shows calibrated Live, Min and Max readings for each channel. Min and Max cover the chart's retained samples. Each Settings popup saves the Low Voltage Alarm, High Voltage Alarm and Actual Voltage through the PDM’s existing calibration API. Editing only alarms preserves calibration. Clearing an edited Actual Voltage resets the offset.

Current PDM/WSI HTTP and firmware authority traffic use TCP 5000. Existing control traffic uses UDP 5000. SRVR serves the same verified bundle and idle rules on legacy TCP 5088 for migration. An older PDM dashboard is detected on TCP 80. See the bootstrap guide for the LAN setup and OTA diagnostics.

The WSI interface on TCP 5000 is tested with a simulated endpoint. Sensor firmware for the WSI remains pending.
