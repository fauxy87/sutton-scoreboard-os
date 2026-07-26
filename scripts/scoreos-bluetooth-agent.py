#!/usr/bin/env python3

import dbus
import dbus.service
import dbus.mainloop.glib

from gi.repository import GLib


BLUEZ_SERVICE = "org.bluez"
AGENT_PATH = "/org/scoreos/bluetooth/agent"
AGENT_INTERFACE = "org.bluez.Agent1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DEVICE_INTERFACE = "org.bluez.Device1"


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class ScoreOSAgent(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, AGENT_PATH)
        self.bus = bus

    def device_details(self, device_path):
        try:
            obj = self.bus.get_object(BLUEZ_SERVICE, device_path)
            props = dbus.Interface(obj, PROPERTIES_INTERFACE)
            values = props.GetAll(DEVICE_INTERFACE)

            return {
                "name": str(
                    values.get("Alias")
                    or values.get("Name")
                    or "Unknown device"
                ),
                "address": str(values.get("Address") or ""),
            }
        except Exception:
            return {
                "name": "Unknown device",
                "address": "",
            }

    def trust_device(self, device_path):
        try:
            obj = self.bus.get_object(BLUEZ_SERVICE, device_path)
            props = dbus.Interface(obj, PROPERTIES_INTERFACE)
            props.Set(
                DEVICE_INTERFACE,
                "Trusted",
                dbus.Boolean(True),
            )

            details = self.device_details(device_path)
            print(
                "Trusted Bluetooth device:",
                details["name"],
                details["address"],
                flush=True,
            )

        except Exception as exc:
            print(
                "Unable to trust device yet:",
                exc,
                flush=True,
            )

        return False

    @dbus.service.method(AGENT_INTERFACE)
    def Release(self):
        print("Bluetooth agent released", flush=True)

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
        out_signature="s",
    )
    def RequestPinCode(self, device):
        details = self.device_details(device)
        print(
            "Legacy PIN requested by",
            details["name"],
            details["address"],
            flush=True,
        )

        return "000000"

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="ou",
    )
    def DisplayPinCode(self, device, pincode):
        details = self.device_details(device)
        print(
            "PIN displayed for",
            details["name"],
            details["address"],
            str(pincode),
            flush=True,
        )

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
        out_signature="u",
    )
    def RequestPasskey(self, device):
        details = self.device_details(device)
        print(
            "Passkey requested by",
            details["name"],
            details["address"],
            flush=True,
        )

        return dbus.UInt32(0)

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="ouq",
    )
    def DisplayPasskey(self, device, passkey, entered):
        details = self.device_details(device)
        print(
            "Passkey for",
            details["name"],
            details["address"],
            f"{int(passkey):06d}",
            flush=True,
        )

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="ou",
    )
    def RequestConfirmation(self, device, passkey):
        details = self.device_details(device)

        print(
            "Automatically confirming",
            f"{int(passkey):06d}",
            "for",
            details["name"],
            details["address"],
            flush=True,
        )

        GLib.timeout_add_seconds(
            2,
            self.trust_device,
            device,
        )

        # Returning successfully confirms the number.
        return

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
    )
    def RequestAuthorization(self, device):
        details = self.device_details(device)

        print(
            "Authorising",
            details["name"],
            details["address"],
            flush=True,
        )

        GLib.timeout_add_seconds(
            2,
            self.trust_device,
            device,
        )

        return

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="os",
    )
    def AuthorizeService(self, device, uuid):
        details = self.device_details(device)

        print(
            "Authorising Bluetooth service",
            uuid,
            "for",
            details["name"],
            details["address"],
            flush=True,
        )

        GLib.timeout_add_seconds(
            2,
            self.trust_device,
            device,
        )

        return

    @dbus.service.method(AGENT_INTERFACE)
    def Cancel(self):
        print("Bluetooth pairing cancelled", flush=True)


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()
    ScoreOSAgent(bus)

    manager_object = bus.get_object(
        BLUEZ_SERVICE,
        "/org/bluez",
    )

    manager = dbus.Interface(
        manager_object,
        "org.bluez.AgentManager1",
    )

    try:
        manager.UnregisterAgent(AGENT_PATH)
    except Exception:
        pass

    manager.RegisterAgent(
        AGENT_PATH,
        "DisplayYesNo",
    )

    manager.RequestDefaultAgent(AGENT_PATH)

    print(
        "SCOREOS Bluetooth agent registered",
        flush=True,
    )

    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
