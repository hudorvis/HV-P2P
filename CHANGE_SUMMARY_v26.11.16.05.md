# HV P2P SYS v26.11.16.05

- The macOS Intel build stopped in the SRVR browser keep-alive test when the next request could no longer retrieve the original PNG.
- The test now processes Qt events while polling for a current PNG, verifies its frame number and dimensions, and checks that requests reuse the original TCP socket.
- The revision updates the release IDs for the complete SRVR and firmware package.
