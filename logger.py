import logging
import sys

def setup_logging(
    verbose: bool = False,
    quiet: bool = False
) -> None:
    """
    Configures the root logger for the application.

    Args:
        verbose: If True, set log level to DEBUG.
        quiet: If True, set log level to ERROR.
    """
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.ERROR

    # Basic configuration
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)-7s] [%(name)-15s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Suppress noisy libraries
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    log = logging.getLogger(__name__)
    log.debug(f"Logging configured. Level set to {logging.getLevelName(level)}")