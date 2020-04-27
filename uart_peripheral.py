#
#   TODO List
#   - clean code
#   - recognize peripheral with local name (not DietPi)
#

import sys
import os, select
import dbus, dbus.mainloop.glib
from gi.repository import GObject
from example_advertisement import Advertisement
from example_advertisement import register_ad_cb, register_ad_error_cb
from example_gatt_server import Service, Characteristic
from example_gatt_server import register_app_cb, register_app_error_cb
 
BLUEZ_SERVICE_NAME =           'org.bluez'
DBUS_OM_IFACE =                'org.freedesktop.DBus.ObjectManager'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
GATT_MANAGER_IFACE =           'org.bluez.GattManager1'
GATT_CHRC_IFACE =              'org.bluez.GattCharacteristic1'
UART_SERVICE_UUID =            '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
UART_RX_CHARACTERISTIC_UUID =  '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
UART_TX_CHARACTERISTIC_UUID =  '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
LOCAL_NAME =                   'RaspberryPi3_UART'

mainloop = None
# apro il Character Device Driver
dev_tx = os.open('/dev/ble_cdev_tx', 0o666, os.O_RDWR)
dev_rx = os.open('/dev/ble_cdev_rx', 0o666, os.O_RDWR)
# Avvio il meccanismo di Epoll
# epoll = select.epoll()

class TxCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(self, bus, index, UART_TX_CHARACTERISTIC_UUID,
                                ['notify'], service)
        self.notifying = False
        # GObject.io_add_watch(sys.stdin, GObject.IO_IN, self.on_console_input)
        # Sposto il watcher sul Character Device Driver
        GObject.io_add_watch(dev_tx, GObject.IO_IN, self.on_cdev_input)
 
    # Commentato il codice che prende il dato dalla console
    # def on_console_input(self, fd, condition):
        # s = fd.readline()
        # if s.isspace():
        #     pass
        # else:
        #     self.send_tx(s)
        # return True

    def on_cdev_input(self, fd, condition):
        # Meccanismo di Epoll
        epoll = select.epoll()
        epoll.register(fd, select.EPOLLIN)
        # try:
        while True:
            events = epoll.poll(1)
            for fileno, event in events:
                if event & select.EPOLLIN:
                    # os.lseek(dev, 0, os.SEEK_SET)
                    self.send_tx(os.read(fd, 16))

                    epoll.unregister(fd)
                    epoll.close()

                    return True
                # Debug
                #         break
                # else:
                #     continue
                # break
        # finally:
        #     epoll.unregister(fd)
        #     epoll.close()
        
        # return True
 
    def send_tx(self, s):
        if not self.notifying:
            return
        value = []
        for c in str(s, encoding='utf-8'):
            value.append(dbus.Byte(c.encode()))
        self.PropertiesChanged(GATT_CHRC_IFACE, {'Value': value}, [])
 
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
 
    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False
 
class RxCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(self, bus, index, UART_RX_CHARACTERISTIC_UUID,
                                ['write'], service)
 
    def WriteValue(self, value, options):
        # print('remote: {}'.format(bytearray(value).decode()))
        # Quando ricevo un dato dal Bluetooth lo scrivo sul Character Device Driver
        os.write(dev_rx, bytearray(value))
 
class UartService(Service):
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, UART_SERVICE_UUID, True)
        self.add_characteristic(TxCharacteristic(bus, 0, self))
        self.add_characteristic(RxCharacteristic(bus, 1, self))
 
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
 
    def get_path(self):
        return dbus.ObjectPath(self.path)
 
    def add_service(self, service):
        self.services.append(service)
 
    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
        return response
 
class UartApplication(Application):
    def __init__(self, bus):
        Application.__init__(self, bus)
        self.add_service(UartService(bus, 0))
 
class UartAdvertisement(Advertisement):
    def __init__(self, bus, index):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.add_service_uuid(UART_SERVICE_UUID)
        self.add_local_name(LOCAL_NAME)
        self.include_tx_power = True
 
# def find_adapter(bus):
#     remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
#                                DBUS_OM_IFACE)
#     objects = remote_om.GetManagedObjects()
#     for o, props in objects.items():
#         for iface in (LE_ADVERTISING_MANAGER_IFACE, GATT_MANAGER_IFACE):
#             if iface not in props:
#                 continue
#         return o
#     return None

def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                                DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for o, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE in props:
            return o
        print('Skip adapter:', o)

    return None
 
def main():
    global mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = find_adapter(bus)
    if not adapter:
        print('BLE adapter not found')
        return
 
    service_manager = dbus.Interface(
                                bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                LE_ADVERTISING_MANAGER_IFACE)

    app = UartApplication(bus)
    adv = UartAdvertisement(bus, 0)
 
    mainloop = GObject.MainLoop()
 
    service_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=register_app_cb,
                                        error_handler=register_app_error_cb)
    ad_manager.RegisterAdvertisement(adv.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    try:
        mainloop.run()
    except KeyboardInterrupt:
        adv.Release()
        # Dai commenti dell'esempio alcune bugfix
        mainloop.quit()
        # Chiudo il Character Device Driver
        os.close(dev_tx)
        os.close(dev_rx)
 
if __name__ == '__main__':
    main()