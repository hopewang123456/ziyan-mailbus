' WSL keep-alive: hold one client session so WSL 2.7.8+ does not recycle
' the idle distro (~60s with no client session kills the distro and docker
' containers restart with the engine). Launched silently at logon by the
' Startup-folder copy of this file. Change the distro name below if needed.
Set sh = CreateObject("WScript.Shell")
sh.Run "wsl.exe -d Ubuntu -- /bin/sh -c ""exec sleep infinity""", 0, False
