from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("cocotbext-spi")
except PackageNotFoundError:
    pass
