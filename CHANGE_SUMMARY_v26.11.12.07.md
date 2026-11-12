# HV P2P SYS v26.11.12.07

- W1P firmware downloads and the fallback upload wait for the selected CTRL to verify the bundled release. Installed W1P units can read the manifest while the gate is closed.
- SRVR holds the verified firmware bytes for the running release. Startup checks the embedded identities of CTRL, W1P and optional PDM images.
- CTRL keeps its retry backoff across repeated announcements. Failed EdgeBox transfers clear update progress so recovery can proceed.
- SRVR can edit long legacy PDM labels and retains the device's existing validation for new names.
- The five-component source package includes the audit, source checks, Olimex bootstrap instructions and commissioning checklist.
