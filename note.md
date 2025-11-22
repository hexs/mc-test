```
pi@raspberrypi:~/PythonProjects/mc-test $ ifconfig
eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.3.1  netmask 255.255.255.0  broadcast 192.168.3.255
        inet6 fe80::62ef:1243:9097:d0c2  prefixlen 64  scopeid 0x20<link>
        ether 88:a2:9e:38:b9:3d  txqueuelen 1000  (Ethernet)
        RX packets 22  bytes 2100 (2.0 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 303  bytes 51189 (49.9 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device interrupt 113  

lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0
        inet6 ::1  prefixlen 128  scopeid 0x10<host>
        loop  txqueuelen 1000  (Local Loopback)
        RX packets 1024  bytes 85769 (83.7 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 1024  bytes 85769 (83.7 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

wlan0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.133.70.248  netmask 255.255.255.0  broadcast 10.133.70.255
        inet6 fe80::ad8f:3485:e395:8287  prefixlen 64  scopeid 0x20<link>
        ether 88:a2:9e:38:b9:3e  txqueuelen 1000  (Ethernet)
        RX packets 49  bytes 13793 (13.4 KiB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 95  bytes 12519 (12.2 KiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

pi@raspberrypi:~/PythonProjects/mc-test $ python v3.py 
Traceback (most recent call last):
  File "/home/pi/PythonProjects/mc-test/v3.py", line 414, in <module>
    main()
    ~~~~^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 375, in main
    plc.write_y(0,plc.read_y(0, 1))
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 365, in write_y
    self._cmd(0x02, self.DEV_Y, head, len(vals), data)
    ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/PythonProjects/mc-test/v3.py", line 266, in _cmd
    raise MCError(f"Command failed (both spec/swap modes): {last_err}")
MCError: Command failed (both spec/swap modes): [Errno 111] Connection refused
```
