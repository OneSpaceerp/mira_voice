# telephony/coturn/

Official `coturn/coturn:4.19.2-trixie` plus an entrypoint that writes `turnserver.conf` from the environment (keeps `TURN_SECRET` off the command line). Listens on 3478 UDP/TCP, relays on UDP 15000–19999, TURN REST API auth (`use-auth-secret`), and may relay only to this server's own IP (all private and loopback ranges denied). Mira Core will issue short-lived TURN credentials to agents (task 1.7).
