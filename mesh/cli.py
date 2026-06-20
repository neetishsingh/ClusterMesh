"""Unified CLI for pip-installed ClusterMesh."""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser

from mesh import __version__


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _require_zeroconf(feature: str) -> bool:
    try:
        import zeroconf  # noqa: F401
        return True
    except ImportError:
        print(
            f"Error: {feature} requires zeroconf.\n"
            "  pip install -e \".[discovery]\"\n"
            "  pip install zeroconf",
            file=sys.stderr,
        )
        return False


def cmd_join(args: argparse.Namespace) -> int:
    import os

    from mesh.agent.config import AgentConfig
    from mesh.worker.runtime import WorkerRuntime

    config = AgentConfig.from_env()
    if args.location:
        config.location = args.location
    if args.node_id:
        config.node_id = args.node_id
    if args.agent_addr:
        config.agent_address = args.agent_addr
    config.preemptible = not args.no_preempt

    driver = args.driver or os.environ.get("MESH_DRIVER_ADDRESS")

    if args.discover:
        if not _require_zeroconf("Auto-discovery"):
            return 1
        from mesh.discovery.mdns import discover_driver

        record = discover_driver(timeout=8.0)
        if not record:
            print("Error: no driver found via mDNS", file=sys.stderr)
            return 1
        config.driver_address = record.grpc_address
        if not args.location:
            config.location = record.site
        print(f"Discovered driver at {record.grpc_address} (site={record.site})")
    elif driver:
        config.driver_address = driver
    elif config.driver_address:
        pass
    else:
        print(
            "Error: driver address required (e.g. 192.168.1.10:50050) "
            "or use --discover",
            file=sys.stderr,
        )
        return 1

    runtime = WorkerRuntime(
        config,
        ui_port=args.ui_port,
        ui_host=args.ui_host,
    )

    print("")
    print("  ClusterMesh Worker")
    print("  ─────────────────────────────────────")
    print(f"  Driver:     {config.driver_address}")
    print(f"  Node:       {config.node_id}")
    print(f"  Site:       {config.location}")
    print(f"  Local UI:   {runtime.local_ui_url}")
    print("  ─────────────────────────────────────")
    print("  Press Ctrl+C to stop")
    print("")

    if args.open:
        webbrowser.open(runtime.local_ui_url)

    try:
        runtime.start(blocking=True)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_platform(args: argparse.Namespace) -> int:
    if args.mdns and not _require_zeroconf("mDNS advertising"):
        return 1

    from mesh.api.server import main as platform_main

    argv = ["mesh-platform"]
    if args.port:
        argv.extend(["--port", str(args.port)])
    if args.db:
        argv.extend(["--db", args.db])
    if args.site:
        argv.extend(["--site", args.site])
    if args.mesh_config:
        argv.extend(["--mesh-config", args.mesh_config])
    if args.mdns:
        argv.append("--mdns")
    sys.argv = argv
    platform_main()
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"clustermesh {__version__}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="clustermesh",
        description="ClusterMesh — join idle machines to an elastic compute cluster",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command")

    join = sub.add_parser(
        "join",
        help="Join a cluster as a worker (agent + local UI)",
        description="Install is: pip install clustermesh && clustermesh join DRIVER:50050",
    )
    join.add_argument(
        "driver",
        nargs="?",
        help="Driver address host:50050 (or set MESH_DRIVER_ADDRESS)",
    )
    join.add_argument("--discover", action="store_true", help="Auto-find driver on LAN (mDNS)")
    join.add_argument("--location", "-l", help="Site/location label")
    join.add_argument("--node-id", help="Override node identifier (default: hostname)")
    join.add_argument("--agent-addr", default="0.0.0.0:50051", help="Agent gRPC bind address")
    join.add_argument("--ui-port", type=int, default=50052, help="Local worker UI port")
    join.add_argument("--ui-host", default="127.0.0.1", help="Local worker UI bind host")
    join.add_argument("--open", action="store_true", help="Open worker UI in browser")
    join.add_argument("--no-preempt", action="store_true", help="Disable user-activity preemption")
    join.set_defaults(func=cmd_join)

    worker = sub.add_parser("worker", help="Alias for clustermesh join")
    worker.add_argument("driver", nargs="?", help="Driver address host:50050")
    worker.add_argument("--discover", action="store_true")
    worker.add_argument("--location", "-l")
    worker.add_argument("--node-id")
    worker.add_argument("--agent-addr", default="0.0.0.0:50051")
    worker.add_argument("--ui-port", type=int, default=50052)
    worker.add_argument("--ui-host", default="127.0.0.1")
    worker.add_argument("--open", action="store_true")
    worker.add_argument("--no-preempt", action="store_true")
    worker.set_defaults(func=cmd_join)

    plat = sub.add_parser("platform", help="Run driver + cluster dashboard")
    plat.add_argument("--port", type=int, default=8080)
    plat.add_argument("--db", default="clustermesh.db")
    plat.add_argument("--site", default="default")
    plat.add_argument("--mesh-config", default=None)
    plat.add_argument("--mdns", action="store_true")
    plat.set_defaults(func=cmd_platform)

    ver = sub.add_parser("version", help="Show version")
    ver.set_defaults(func=cmd_version)

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        print("\nQuick start on any machine:\n  pip install clustermesh\n  clustermesh join 192.168.1.10:50050 --open\n")
        sys.exit(0)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
