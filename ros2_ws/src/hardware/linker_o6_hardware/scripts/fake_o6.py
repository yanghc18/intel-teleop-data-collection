#!/usr/bin/env python3
"""Fake Linker O6 hand on SocketCAN (e.g. vcan) for testing linker_o6_hardware without the device."""

import argparse
import time

import can

HAND_IDS = {'left': 0x28, 'right': 0x27}
CMD_POSITION, CMD_TORQUE, CMD_SPEED = 0x01, 0x02, 0x05


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', required=True, help='CAN interface, e.g. hand_r')
    parser.add_argument('--side', choices=HAND_IDS, required=True)
    parser.add_argument('--rate', type=float, default=500.0, help='max finger speed in raw units/s')
    parser.add_argument('--silent', action='store_true', help='never answer (to test the state timeout)')
    args = parser.parse_args()

    can_id = HAND_IDS[args.side]
    state = [200.0, 255.0, 255.0, 255.0, 255.0, 180.0]  # SDK power-on pose
    target = list(state)
    regs = {CMD_TORQUE: [255] * 6, CMD_SPEED: [255] * 6}
    last = time.monotonic()

    with can.Bus(channel=args.channel, interface='socketcan') as bus:
        print(f'fake O6 {args.side} on {args.channel}, ID 0x{can_id:02X}', flush=True)
        while True:
            msg = bus.recv(timeout=0.002)
            now = time.monotonic()
            step = args.rate * (now - last)
            last = now
            state = [s + max(-step, min(step, t - s)) for s, t in zip(state, target)]

            if msg is None or msg.arbitration_id != can_id or not msg.data or args.silent:
                continue
            cmd, payload = msg.data[0], list(msg.data[1:])
            if cmd == CMD_POSITION:
                if len(payload) == 6:
                    target = [float(v) for v in payload]
                reply = [round(s) for s in state]
            elif cmd in regs:
                if len(payload) == 6:
                    regs[cmd] = payload
                reply = regs[cmd]
            else:
                continue
            bus.send(can.Message(arbitration_id=can_id, data=[cmd] + reply, is_extended_id=False))


if __name__ == '__main__':
    main()
