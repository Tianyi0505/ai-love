# Live Edge Runtime

LiveEdgeService hosts AvatarModule and StreamModule. Start the service with python -m live.edge_service.

## Module results

| Module | Input contract | Responsibility |
| --- | --- | --- |
| AvatarModule | avatar.command.> and AvatarCommand | Sends avatar and stage events. |
| StreamModule | obs.control and StreamControl | Sends OBS and stream-control events. |

Each module owns its subscription handle. The host owns shared connections. The agent owns response generation.

service.live-edge defines the service address, OBS WebSocket URL, and stream key reference. Deployment secrets provide live credentials.
