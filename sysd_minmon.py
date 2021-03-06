#!/usr/bin/env python2

def main():
    import argparse
    import subprocess
    import sys

    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    import gobject

    def dprint(message):
        print(message)
        sys.stdout.flush()

    parser = argparse.ArgumentParser(
        description='A daemon to monitor systemd units.',
    )
    parser.add_argument(
        'script', 
        help='Script to call on state changes.',
        nargs=1,
    )
    parser.add_argument(
        'units', 
        help='Unit(s) to watch.',
        nargs='*', 
    )
    parser.add_argument(
        '-u', 
        '--user', 
        help='Monitor user rather than system instance.', 
        action='store_true', 
        default=False,
    )
    args = parser.parse_args()

    DBusGMainLoop(set_as_default=True)
    if args.user:
        bus = dbus.SessionBus()
    else:
        bus = dbus.SystemBus()

    systemd_obj = bus.get_object(
        'org.freedesktop.systemd1', 
        '/org/freedesktop/systemd1',
    )
    systemd = dbus.Interface(systemd_obj, 'org.freedesktop.systemd1.Manager')

    def react(name):
        def inner(*pargs, **kwargs):
            if pargs[0] == 'org.freedesktop.systemd1.Unit':
                subprocess.Popen([
                    args.script[0], 
                    name, 
                    pargs[1]['ActiveState'],
                    'user' if args.user else 'system',
                ])
        return inner

    signals = {}

    def attach(unit_name, unit_path=None):
        dprint('Attaching: {}'.format(unit_name))
        if not unit_path:
            unit_path = systemd.GetUnit(unit_name)
        unit_obj = bus.get_object('org.freedesktop.systemd1', unit_path)
        unit_props = dbus.Interface(
            unit_obj, 
            'org.freedesktop.DBus.Properties',
        )
        if unit_name in signals:
            signals[unit_name].remove()
        signals[unit_name] = unit_props.connect_to_signal(
            'PropertiesChanged', 
            react(unit_name),
        )
        dprint('{} attached signals'.format(len(signals)))

    def handle_new(unit_name, unit_path):
        if unit_name not in args.units:
            return
        attach(unit_name, unit_path)
    systemd.connect_to_signal('UnitNew', handle_new)

    def handle_remove(unit_name, unit_path):
        if unit_name not in args.units:
            return
        if unit_name not in signals:
            return
        dprint('Detaching: {}'.format(unit_name))
        signals[unit_name].remove()
        del signals[unit_name]
        dprint('{} attached signals'.format(len(signals)))
    systemd.connect_to_signal('UnitRemove', handle_remove)

    for unit_name in args.units:
        try:
            attach(unit_name)
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == 'org.freedesktop.systemd1.NoSuchUnit':
                continue
            raise

    lifeline = dbus.service.BusName('com.zarbosoft.sysd_minmon', bus=bus)
    loop = gobject.MainLoop()
    loop.run()

if __name__ == '__main__':
    main()
