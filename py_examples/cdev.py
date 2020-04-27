#!/usr/bin/python
import os
import select

data = b'xxxx'
dev = os.open("/dev/mychardev-0", os.O_RDWR)
os.write(dev, data)

epoll = select.epoll()
epoll.register(dev, select.EPOLLIN)
try:
    while True:
        events = epoll.poll(1)
        for fileno, event in events:
            if event & select.EPOLLIN:
                # os.lseek(dev, 0, os.SEEK_SET)
                print(os.read(dev, 16))

finally:
    epoll.unregister(dev)
    epoll.close()
    os.close(dev)
