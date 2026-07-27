#!/usr/bin/env python3

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

import sys

PROJECT_ROOT = "/home/pi/sutton-scoreboard-os"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from arduino.connection import ArduinoConnection
from engine.runtime import ScoreboardEngine
from engine.live_diagnostics import initialise, packet_received

initialise()

arduino = ArduinoConnection()

arduino.connect()
scoreboard_engine = ScoreboardEngine(arduino)

BLUEZ_SERVICE = "org.bluez"
DBUS_OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"

GATT_MANAGER = "org.bluez.GattManager1"

GATT_SERVICE = "org.bluez.GattService1"
GATT_CHARACTERISTIC = "org.bluez.GattCharacteristic1"

SERVICE_UUID = "5a0d6a15-b664-4304-8530-3a0ec53e5bc1"
CHARACTERISTIC_UUID = "df531f62-fc0b-40ce-81b2-32a6262ea440"
LOCAL_NAME = "FoSCC-Scoreboard-TGT"


class InvalidArguments(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"



class Characteristic(dbus.service.Object):
    def __init__(self, bus, service_path):
        self.path = service_path + "/characteristic0"
        self.service_path = service_path
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_CHARACTERISTIC: {
                "Service": dbus.ObjectPath(self.service_path),
                "UUID": dbus.String(CHARACTERISTIC_UUID),
                "Flags": dbus.Array(
                    ["write", "write-without-response"],
                    signature="s",
                ),
            }
        }

    @dbus.service.method(
        DBUS_PROPERTIES,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC:
            raise InvalidArguments()

        return self.get_properties()[GATT_CHARACTERISTIC]

    @dbus.service.method(
        GATT_CHARACTERISTIC,
        in_signature="aya{sv}",
        out_signature="",
    )
    def WriteValue(self, value, options):
        packet = bytes(bytearray(value)).decode(
            "utf-8",
            errors="replace",
        ).strip()
      
        packet_received()
        scoreboard_engine.receive_packet(packet)



class Service(dbus.service.Object):
    PATH = "/org/suttoncc/scoreboard/service0"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)
        self.characteristic = Characteristic(bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    def get_properties(self):
        return {
            GATT_SERVICE: {
                "Primary": dbus.Boolean(True),
                "UUID": dbus.String(SERVICE_UUID),
            }
        }

    @dbus.service.method(
        DBUS_PROPERTIES,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface):
        if interface != GATT_SERVICE:
            raise InvalidArguments()

        return self.get_properties()[GATT_SERVICE]


class Application(dbus.service.Object):
    PATH = "/"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)
        self.service = Service(bus)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    @dbus.service.method(
        DBUS_OBJECT_MANAGER,
        out_signature="a{oa{sa{sv}}}",
    )
    def GetManagedObjects(self):
        objects = {
            self.service.get_path(): self.service.get_properties(),
            self.service.characteristic.get_path():
                self.service.characteristic.get_properties(),
        }

        print("GetManagedObjects called")
        print("GATT objects:", objects)

        return objects


def find_adapter(bus):
    preferred_address = "18:69:45:F3:58:B9"

    manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE, "/"),
        DBUS_OBJECT_MANAGER,
    )

    objects = manager.GetManagedObjects()

    for path, interfaces in objects.items():
        adapter_properties = interfaces.get("org.bluez.Adapter1")

        if (
            adapter_properties
            and GATT_MANAGER in interfaces
            and str(adapter_properties.get("Address", "")).upper()
                == preferred_address
        ):
            return path

    return None


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()
    adapter_path = find_adapter(bus)
    print("Using Bluetooth adapter:", adapter_path)

    if adapter_path is None:
        raise RuntimeError("No BLE adapter found")

    adapter = bus.get_object(BLUEZ_SERVICE, adapter_path)

    gatt_manager = dbus.Interface(
        adapter,
        GATT_MANAGER,
    )
 


    application = Application(bus)
    mainloop = GLib.MainLoop()

    def app_registered():
        print("GATT application registered")

        from web.startup import startup_manager

        startup_manager.set_stage(
            "bluetooth",
            "✓ Bluetooth GATT service registered",
        )

        startup_manager.add_log(
            "✓ Match engine ready"
        )

        startup_manager.set_stage(
            "ready",
            "✓ SCOREOS ready for play",
        )


    def app_failed(error):
        print("GATT registration failed:", error)

        mainloop.quit()



        from web.startup import startup_manager

        startup_manager.set_stage(
            "bluetooth",
            "✓ Bluetooth advertising",
        )

    gatt_manager.RegisterApplication(
        application.get_path(),
        {},
        reply_handler=app_registered,
        error_handler=app_failed,
    )


    print("Starting Sutton Scoreboard OS")
    mainloop.run()


if __name__ == "__main__":
    main()
