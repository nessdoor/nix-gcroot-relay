import argparse
import json
import logging
import systemd.daemon as sd
from collections.abc import Iterable, Iterator
from hashlib import sha1
from itertools import takewhile
from pathlib import Path
from sys import stdin
from typing import TextIO
from uuid import UUID

description ="Receive updates about currently valid GC roots inside a VM."
parser = argparse.ArgumentParser(description=description)
parser.add_argument("-v", "--verbose",
                    action='store_true',
                    help="Print debug messages")
parser.add_argument("-s", "--store",
                    type=Path, default=Path("/nix/store"),
                    help="Path to the Nix store (default: /nix/store)")
parser.add_argument("-r", "--gcroots",
                    type=Path, default=Path("/nix/var/nix/gcroots"),
                    help="Path to per-vm GC roots (default: /nix/var/nix/gcroots/per-vm)")


def lines(f: TextIO) -> Iterator[str]:
    while True:
        yield f.readline()


def json_stream(f: TextIO) -> Iterator[dict[str,object]]:
    # readline() should return an empty string upon termination
    for line in takewhile(lambda l: len(l) > 0, lines(f)):
        logging.debug("Received:\n" + line)
        yield json.loads(line)


def parse_paths(ps: Iterable[list[str]]) -> Iterator[tuple[Path, Path]]:
    for pp in ps:
        # Normalize GC root path by hashing
        yield (Path(sha1(pp[0].encode('utf-8'),
                         usedforsecurity=False).hexdigest()),
               Path(pp[1]))


def register_roots(roots_dir: Path, store_path: Path,
                   roots: Iterable[tuple[Path, Path]]) -> None:
    for r, d in roots:
        rr = (roots_dir / r) # r is guaranteed to be a hash
        if not d.is_relative_to(store_path):
            # Prevent arbitrary linking of paths from other locations
            logging.warning(
                "GC root destination {} points outside store path {}; ignoring."
                .format(rr, store_path))
        else:
            logging.debug("Registering new root {}.".format(rr))
            rr.symlink_to(d)


def unregister_roots(roots_dir: Path,
                     roots: Iterable[tuple[Path, object]]) -> None:
    for r, _ in roots:
        rr = (roots_dir / r) # r is guaranteed to be a hash
        logging.debug("Deleting root {}.".format(rr))
        rr.unlink(missing_ok=True)


def main(store_path: Path, gcroots_dir: Path) -> None:
    logging.debug("Opening stream...");
    # Use either the sockets passed to us by Systemd or read from stdin
    listen_fds = sd.listen_fds()
    if len(listen_fds) > 0:
        logging.debug("Opening Systemd-supplied socket on fd {}..."
                      .format(listen_fds[0]))
        f = open(listen_fds[0])
        logging.debug("Socket opened.")
    else:
        logging.debug("Reading from stdin.")
        f = stdin

    with f:
        js = json_stream(f)

        # Read the initial registration message
        logging.debug("Registering client...")
        initial = next(js)
        client_id = UUID(initial["id"])
        roots = parse_paths(initial["roots"])

        # Initialize the roots directory
        vm_gcroots = gcroots_dir / str(client_id)
        logging.info("Registered client {}. Store path: {}. GC roots: {}."
                     .format(client_id, store_path, vm_gcroots))
        logging.debug("Initializing GC root directory {}...".format(vm_gcroots))
        vm_gcroots.mkdir(parents=True, exist_ok=True)
        # Cleanup any pre-existing links
        logging.debug("Clearing previous roots...")
        for link in vm_gcroots.iterdir():
            logging.debug("Deleting root {}.".format(link))
            link.unlink(missing_ok=True) # Might be racing against the GC
        # Create the initial roots
        logging.debug("Populating directory with the initial roots...")
        register_roots(vm_gcroots, store_path, roots)

        # Begin processing updates
        sd.notify("READY=1\nSTATUS=Serving requests from {}".format(client_id))
        logging.info("Listening for periodic updates...")
        for update in js:
            logging.debug("Update received. Resuming operations...")
            unregister_roots(vm_gcroots, parse_paths(update["removed"]))
            register_roots(vm_gcroots, store_path, parse_paths(update["added"]))
            logging.debug("Finished processing updates. Sleeping...")

        # Orderly exit
        sd.notify("STOPPING=1\nSTATUS=Shutting down...")
        logging.debug("Exiting...")


if __name__ == "__main__":
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    main(store_path=args.store.resolve(), gcroots_dir=args.gcroots.resolve())
