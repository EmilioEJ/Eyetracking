"""Punto de entrada: python -m gazescope [--source webcam|mouse] [--monitor N] [--hidden]."""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="gazescope", description="Eye tracking con webcam y mapas de calor")
    parser.add_argument("--source", choices=("webcam", "mouse"), default="webcam",
                        help="webcam (por defecto) o mouse para simular la mirada con el cursor")
    parser.add_argument("--monitor", type=int, default=None, help="índice del monitor a rastrear")
    parser.add_argument("--hidden", action="store_true", help="arrancar minimizado en la bandeja")
    args = parser.parse_args()

    from .app import run

    return run(args.source, args.monitor, args.hidden)


if __name__ == "__main__":
    sys.exit(main())
