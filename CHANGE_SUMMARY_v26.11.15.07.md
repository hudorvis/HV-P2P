# HV P2P SYS v26.11.15.07

- Serve a new SRVR image as soon as it is available. Reuse browser TCP connections and deliver browser actions to the Qt event loop as they arrive.
- Apply the frame size limit in physical pixels and composite the entire image on high-DPI displays. The live view fits the browser viewport at its original proportions.
- Reduce repeated Free-D and cable-chart calculations. Reuse the geometry preparation across plot samples and include the calibrated span in the preview cache.
- Deliver grouped browser wheel deltas to the Qt control under the pointer, support Space on focused buttons and open PDM and WSI Web UI on the initiating browser.
