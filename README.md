# SPI Interface for Cocotb

[![Regression Tests](https://github.com/schang412/cocotbext-spi/actions/workflows/regression-tests.yml/badge.svg)](https://github.com/schang412/cocotbext-spi/actions/workflows/regression-tests.yml)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

GitHub repository: https://github.com/schang412/cocotbext-spi

## Introduction

SPI simulation framework for [cocotb](https://github.com/cocotb/cocotb).

## Installation

Installation from pip (release version, stable):
```bash
pip install cocotbext-spi
```

Installation from git (latest development version, potentially unstable):
```bash
pip install https://github.com/schang412/cocotbext-spi/archive/main.zip
```

Installation for active development:
```bash
git clone https://github.com/schang412/cocotbext-spi
pip install -e cocotbext-spi
```

## Documentation and Usage

See the `tests` directory for complete testbenches using these modules.

### SPI Signals

The SPI bus signals are bundled together into a `SpiBus` class.

If the port instantiations look like:
```verilog
module my_module(
    input  wire sclk,
    input  wire mosi,
    output wire miso,
    input  wire cs,  // active-low
)
```
The `SpiBus` class can be created as:
```python
from cocotbext.spi import SpiBus
spi_bus = SpiBus.from_entity(dut)
```

If there is some prefix, the `from_prefix` class method may be used:
```verilog
module my_module(
    input  wire spi0_sclk,
    input  wire spi0_mosi,
    output wire spi0_miso,
    input  wire spi0_cs,  // active-low
)
```
```python
spi_bus = SpiBus.from_prefix(dut, "spi0")
```

If some signals do not conform to the expected naming scheme, it is possible to use the `[cocotb_bus](https://cocotb-bus.readthedocs.io/en/latest/library_reference.html#cocotb_bus.bus.Bus)` syntax:
```verilog
module my_module(
    input  wire spi0_A_sclkxDI,
    input  wire spi0_B_mosixDI,
    output wire spi0_C_misoxDO,
    input  wire spi0_D_ncsxDI,  // active-low
)
```
```python
spi_bus = SpiBus(entity = dut,
                 name = "spi0",
                 signals = {
                            'sclk' : 'A_sclkxDI',
                            'mosi' : 'B_mosixDI',
                            'miso' : 'C_misoxDO',
                            'cs'   : 'D_ncsxDI'
                           })
```

### SPI Config

SPI Configuration parameters are bundled together into a `SpiConfig` class.

To create the object simply call it like a class and pass in arguments:
```python
from cocotbext.spi import SpiConfig

spi_config = SpiConfig(
    word_width = 16,        # number of bits in a SPI transaction
    sclk_freq  = 25e6,      # clock rate in Hz
    cpol       = False,     # clock idle polarity
    cpha       = True,      # clock phase (CPHA=True means data sampled on second edge)
    msb_first  = True,      # the order that bits are clocked onto the wire
    data_output_idle = 1,   # the idle value of the MOSI or MISO line
    frame_spacing_ns = 1,   # the spacing between frames that the master waits for or the slave obeys
                            #       the slave should raise SpiFrameError if this is not obeyed.
    ignore_rx_value = None, # MISO value that should be ignored when received
    cs_active_low = True    # the chip select is active low
)
```

All parameters are optional, and the defaults are shown above.

### SPI Master

The `SpiMaster` class acts as an SPI Master endpoint.

To use this class, import it, configure it, and connect to the dut.

```python
from cocotbext.spi import SpiMaster, SpiBus, SpiConfig

spi_bus = SpiBus.from_entity(dut)

spi_config = SpiConfig(
    word_width = 16,     # all parameters optional
    sclk_freq  = 25e6,   # these are the defaults
    cpol       = False,
    cpha       = True,
    msb_first  = True,
    cs_active_low = True # optional (assumed True)
)

spi_master = SpiMaster(spi_bus, spi_config)
```

To send data into a design with `SpiMaster`, call `write()` or `write_nowait()`. Accepted data types are iterables of ints including lists, bytes, bytearrays, etc. Optionally, call wait() to wait for the transmit operation to complete. We can take a look at the data received back with `read()` or `read_nowait()`

```python
# TX/RX transaction example
spi_master.write_nowait([0xFFFF])
await spi_master.wait()
read_bytes = await spi_master.read()
print(read_bytes)

# we can alternatively call (which has equivalent functionality)
await spi_master.write([0xFFFF])
read_bytes = await spi_masetr.read()
```

#### Constructor Parameters
- `bus`: SpiBus
- `config`: SpiConfig

#### Methods
- `write(data)`: send data (blocking)
- `write_nowait(data)`: send data (non-blocking)
- `read(count=-1)`: read count bytes from buffer, reading whole buffer by default (blocking)
- `read_nowait(count=-1)`: read count bytes from buffer, reading whole buffer by default (non-blocking)
- `count_tx()`: returns the number of items in the transmit queue
- `count_rx()`: returns the number of items in the receive queue
- `empty_tx()`: returns True if the transmit queue is empty
- `empty_rx()`: returns True if the receive queue is empty
- `idle()`: returns True if the transmit and receive buffers are empty
- `clear()`: drop all data in the queue

### SPI Slave

The `SpiSlaveBase` acts as an abstract class for a SPI Slave Endpoint.

To use this class, import it and inherit it. Then use the subclass as the slave and connect it to the dut.

```python
from cocotbext.spi import SpiMaster, SpiBus, SpiConfig

class SimpleSpiSlave(SpiSlaveBase):
    def __init__(self, bus):
        self._config = SpiConfig()
        self.content = 0
        super().__init__(bus)

    async def get_content(self):
        await self.idle.wait()
        return self.content

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        self.content = int(await self._shift(16, tx_word=(0xAAAA)))

        await frame_end

spi_slave = SimpleSpiSlave(SpiBus.from_entity(dut))
```

#### Implementation

All SPI Slave Classes should:
- inherit the SpiSlaveBase class
- define `self._config` adjust the values for:
    - `word_width`
    - `cpha`
    - `cpol`
    - `msb_first`
    - `frame_spacing_ns`
- implement a `_transaction` coroutine
    - the coroutine should take 3 arguments, self, frame_start and frame_end
    - the coroutine should await frame_start at the transaction start, and frame_end when done.
        - frame_start and frame_end are Rising and Falling edges of the chip select based on the chip select polarity
    - when the coroutine receives a frame_start signal, it should clear the `self.idle` Event.
        - `self.idle` is automatically set when `_transaction` returns
- when implementing a method to read the class contents, make sure to await the `self.idle`, otherwise the data may not be up to date because the device is in the middle of a transaction.


#### Simulated Devices

This framework includes some SPI Slave devices built in. A list of supported devices can be found in `cocotbext/spi/devices` and are sorted by vendor.

To use these devices, you can simply import them.

```python
from cocotbext.spi.devices.TI import DRV8306

spi_slave = DRV8306(SpiBus.from_entity(dut, cs_name="ncs"))
```

To submit a new device, make a pull request.
