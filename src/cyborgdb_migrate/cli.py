import argparse
import sys

from cyborgdb_migrate import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="cyborgdb-migrate",
        description="Migrate vector data from other databases into CyborgDB",
    )
    parser.add_argument(
        "--config", metavar="FILE",
        help="TOML config file for non-interactive mode",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from checkpoint (non-interactive only)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Vectors per batch (default: 100)",
    )
    parser.add_argument(
        "--log-file", metavar="FILE",
        default="./cyborgdb-migrate.log",
        help="Log file path (default: ./cyborgdb-migrate.log)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Minimal output (non-interactive only)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    if args.config:
        setup_logging(args.log_file)
        run_headless(args.config, args.batch_size, args.resume, args.log_file, args.quiet)
    else:
        if args.resume:
            print("Error: --resume is only supported with --config", file=sys.stderr)
            raise SystemExit(1)
        setup_logging(args.log_file)
        from cyborgdb_migrate.app import MigrateApp
        from cyborgdb_migrate.models import MigrationState

        state = MigrationState()
        state.batch_size = args.batch_size
        app = MigrateApp(state)
        app.run()


def setup_logging(log_file: str) -> None:
    import logging

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_headless(
    config_path: str,
    batch_size: int,
    resume: bool,
    log_file: str,
    quiet: bool,
) -> None:
    import logging
    import threading

    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    from cyborgdb_migrate.config import load_config
    from cyborgdb_migrate.destination import CyborgDestination
    from cyborgdb_migrate.engine import MigrationEngine
    from cyborgdb_migrate.sources import SOURCE_REGISTRY

    logger = logging.getLogger("cyborgdb_migrate.headless")
    console = Console(stderr=True)

    config = load_config(config_path)

    # Override batch_size from CLI if provided and different from default
    if batch_size != 100:
        config.batch_size = batch_size

    # Resolve source
    source_type = config.source_type
    source_cls = None
    for name, cls in SOURCE_REGISTRY.items():
        if name.lower() == source_type.lower() or source_type.lower() in name.lower():
            source_cls = cls
            break
    if source_cls is None:
        console.print(f"[red]Unknown source type: {source_type}[/red]")
        raise SystemExit(1)

    source = source_cls()
    source.configure(config.source_credentials)
    if not quiet:
        console.print(f"Connecting to {source.name()}...")
    source.connect()
    if not quiet:
        console.print(f"[green]Connected to {source.name()}[/green]")

    # Inspect source
    source_info = source.inspect(config.source_index)
    if not quiet:
        console.print(
            f"Source: {source_info.index_or_collection_name} "
            f"({source_info.dimension}d, {source_info.vector_count:,} vectors)"
        )

    # Connect to CyborgDB
    destination = CyborgDestination()
    destination.connect(config.destination_host, config.destination_api_key)
    if not quiet:
        console.print("[green]Connected to CyborgDB[/green]")

    # Set up index
    if config.create_index:
        from cyborgdb import Client

        index_key = Client.generate_key(save=False)
        if not quiet:
            console.print(f"Generated encryption key (hex): {index_key.hex()}")

        from cyborgdb_migrate.destination import compute_n_lists

        n_lists = compute_n_lists(source_info.vector_count)
        destination.create_index(
            name=config.index_name,
            dimension=source_info.dimension,
            index_type=config.index_type or "ivfflat",
            index_key=index_key,
            n_lists=n_lists,
            metric=source_info.metric,
        )
    else:
        if config.index_key:
            index_key = _decode_key(config.index_key)
        elif config.key_file:
            with open(config.key_file) as f:
                index_key = _decode_key(f.read().strip())
        else:
            console.print("[red]No index key provided for existing index[/red]")
            raise SystemExit(1)
        destination.load_index(config.index_name, index_key)

        # Validate dimension match for existing index
        dest_dim = destination.get_index_dimension()
        if dest_dim is not None and dest_dim != source_info.dimension:
            console.print(
                f"[red]Dimension mismatch: source has {source_info.dimension}d, "
                f"destination has {dest_dim}d[/red]"
            )
            raise SystemExit(1)

    # Run migration
    cancel_event = threading.Event()

    def on_progress(update):
        pass  # Progress handled by rich progress bar below

    engine = MigrationEngine(
        source=source,
        destination=destination,
        source_info=source_info,
        batch_size=config.batch_size,
        checkpoint_every=config.checkpoint_every,
        spot_check_per_batch=config.spot_check_per_batch,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )

    if quiet:
        result = engine.run(
            namespace=config.source_namespace,
            resume=resume,
        )
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Migrating...", total=source_info.vector_count)

            def progress_callback(update):
                progress.update(task, completed=update.vectors_migrated)

            engine.on_progress = progress_callback
            result = engine.run(
                namespace=config.source_namespace,
                resume=resume,
            )

    if not quiet:
        console.print("\n[green]Migration complete![/green]")
        console.print(f"  Vectors: {result.vectors_migrated:,} / {result.vectors_expected:,}")
        console.print(f"  Duration: {result.duration_seconds:.1f}s")
        console.print(f"  Spot check: {'PASSED' if result.spot_check_passed else 'FAILED'}")
        console.print(f"  Details: {result.spot_check_details}")

    if not result.spot_check_passed:
        logger.warning("Spot check failed: %s", result.spot_check_details)
        raise SystemExit(2)


def _decode_key(value: str) -> bytes:
    """Decode a key from hex, falling back to base64 for backwards compatibility."""
    try:
        return bytes.fromhex(value)
    except ValueError:
        import base64

        return base64.b64decode(value)
