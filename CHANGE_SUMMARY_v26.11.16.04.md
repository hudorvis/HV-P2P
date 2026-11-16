# HV P2P SYS v26.11.16.04

- SRVR requests STOP and Servo Enable OFF after a validated E-Stop press even if release reaches SRVR before the same motion tick. The stop cancels preset and limit recall and requires the joystick to return to neutral before re-arm.
- W1P sends the local DI0 press and release through its existing STATUS message immediately after handling the transition. This also reports an opening that fits inside the normal 50 ms STATUS interval.
- A firmware verification failure keeps its reported result after 100% transfer. The CTRL-to-CTRL-TS reboot diagnostic prints the reset reason with the matching integer format.
- SRVR destroys the desktop and browser Qt views while their context objects are still live. The source smoke exercises the normal quit callbacks.
