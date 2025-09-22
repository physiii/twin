# RTSP Client (Standalone)

Client scripts live in this `client/` folder. Wrappers provide common tasks and a user-level systemd service.

Usage:

- List devices: `./list-devices.sh`
- One-off run: `RTSP_SERVER_IP=192.168.1.40 RTSP_PATH=office ./start.sh [--device "USB"]`
- Install user service: `./install.sh` (edits `~/.config/rtsp-mic-client.env`)
- Start/Stop service: `./start-service.sh`, `./stop.sh`
- Status/Logs: `./status.sh`, `./logs.sh`
- Remove service: `./remove.sh [--purge]`
- 5s push test: `./test.sh 192.168.1.40 office`
