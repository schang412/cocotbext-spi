try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from pkg_resources import get_distribution, DistributionNotFound

    try:
        __version__ = get_distribution("cocotbext-spi").version
    except DistributionNotFound:
        __version__ = "0.0.0"
else:
    try:
        __version__ = version("cocotbext-spi")
    except PackageNotFoundError:
        __version__ = "0.0.0"
