import argparse
import json
import logging
import time
from pathlib import Path
from socket import socket, AF_VSOCK, SOCK_STREAM
from uuid import UUID


description ="Send updates about currently valid GC roots inside a VM to the hypervisor host (or another VM)."
parser = argparse.ArgumentParser(description=description)
parser.add_argument("-v", "--verbose",
                    action='store_true',
                    help="Print debug messages")
parser.add_argument("-s", "--store",
                    type=Path, default=Path("/nix/store"),
                    help="Path to the Nix store (default: /nix/store)")
parser.add_argument("-r", "--gcroots",
                    type=Path, default=Path("/nix/var/nix/gcroots"),
                    help="Path to GC roots (default: /nix/var/nix/gcroots)")
parser.add_argument("-t", "--interval",
                    type=int, default=300,
                    help="Polling interval in seconds (default: 300s)")
parser.add_argument("-a", "--address",
                    type=int, default=2,
                    help="CID to which updates will be sent (default: 2)")
parser.add_argument("-p", "--port",
                    type=int, default=25565,
                    help="Port to which updates will be sent (default: 25565)")
parser.add_argument("uuid", type=UUID,
                    help="UUID of the VM which is sending the updates")


def resolve_until_store(store_path: Path, p: Path) -> Path | None:
    """Follow the symlink chain until the Nix store is reached. Return None if
    the symlink is dangling.
    """
    try:
        while store_path not in p.parents:
            p = p.readlink()
        return p
    except OSError as e:
        # If the link is dead, a FileNotFoundError will be thrown
        return None


def find_roots(store_path: Path, gcroots_dir: Path) -> dict[Path, Path]:
    """Find the set of currently-valid GC roots."""
    # Walk the entire GC roots directory and produce a list of roots
    files = (d / f for d, _, fs in gcroots_dir.walk() for f in fs)
    roots = list(filter(lambda l: l.is_symlink(), files))

    # Resolve the symlinks until a store path is reached, storing only the roots
    # that point to valid store paths
    store_targets = map(lambda l: resolve_until_store(store_path, l.readlink()), roots)
    valid_root_target_pairs = filter(lambda p: None != p[1], zip(roots, store_targets))
    return dict(valid_root_target_pairs)


def json_to_bytes(obj) -> bytes:
    """Convert a JSON-serializable object into raw bytes."""
    return bytes(json.dumps(obj), encoding='utf-8')


def main(uuid: UUID, store_path: Path, gcroots_dir: Path, interval: int=300,
         cid: int=2, port: int=25565) -> None:
    # State object representing the current set of GC roots
    old_roots = find_roots(store_path, gcroots_dir)

    with socket(family=AF_VSOCK, type=SOCK_STREAM) as s:
        logging.info("Connecting to vsock {}:{}...".format(cid, port))
        s.connect((cid, port))

        # Handshake with the remote listener, stating the identity of the
        # machine and its current set of valid GC roots
        logging.info("Initializing initial set of GC roots...")
        logging.debug("Valid roots:\n" +
                      "\n".join("- {} -> {}".format(r, t)
                                for r, t in old_roots.items()))
        s.sendall(json_to_bytes({"type": "init",
                                 "id": uuid.hex,
                                 "roots": [(str(r), str(t))
                                           for r, t in old_roots.items()]}))

        # Constantly update the set of valid roots by sending differential messages
        logging.info("Periodic update started (interval: {}).".format(interval))
        while True:
            time.sleep(interval)

            logging.debug("Initiating refresh of GC roots...")
            valid_roots = find_roots(store_path, gcroots_dir)
            logging.debug("Valid roots:\n" +
                          "\n".join("- {} -> {}".format(r, t)
                                    for r, t in valid_roots.items()))


            if valid_roots != old_roots:
                logging.debug("Sending differential update.")
                # Calculate the sets of added and removed paths w.r.t. the set of
                # known roots
                new_roots = valid_roots.items() - old_roots.items()
                removed_roots = old_roots.items() - valid_roots.items()
                logging.debug("New:\n" +
                    "\n".join("- {} -> {}".format(r, t)
                              for r, t in new_roots))
                logging.debug("Removed:\n" +
                    "\n".join("- {} -> {}".format(r, t)
                              for r, t in removed_roots))

                s.sendall(json_to_bytes({
                    "type": "update",
                    "added": [(str(r), str(t)) for r, t in new_roots],
                    "removed": [(str(r), str(t)) for r, t in removed_roots]
                }))

                # Replace the set of known roots with a fresh one
                old_roots = valid_roots
                logging.debug("Update sent. Going to sleep...")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    main(uuid=args.uuid,
         store_path=args.store, gcroots_dir=args.gcroots,
         interval=args.interval, cid=args.address, port=args.port)
