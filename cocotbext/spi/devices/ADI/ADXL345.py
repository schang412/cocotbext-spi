from cocotb.triggers import FallingEdge
from cocotb.triggers import First
from cocotb.triggers import RisingEdge

from ...spi import SpiBus
from ...spi import SpiConfig
from ...spi import SpiFrameError
from ...spi import SpiSlaveBase


class ADXL345(SpiSlaveBase):
    _config = SpiConfig(
        # technically, a word is 16 bits long on this chip, but this chip allows for 16+8n bits if the multibyte is set
        word_width=8,
        cpol=True,
        cpha=True,
        msb_first=True,
        frame_spacing_ns=150,
        cs_active_low=True,
    )

    def __init__(self, bus: SpiBus):
        self._registers = {
            0x00: 0b1110_0101,  # DEVID
            0x1D: 0x00,         # Tap Threshold
            0x1E: 0x00,         # OFSX
            0x1F: 0x00,         # OFSY
            0x20: 0x00,         # OFSZ
            0x21: 0x00,         # DUR
            0x22: 0x00,         # LATENT
            0x23: 0x00,         # WINDOW
            0x24: 0x00,         # THRESH_ACT
            0x25: 0x00,         # THRESH_INACT
            0x26: 0x00,         # TIME_INACT
            0x27: 0x00,         # ACT_INACT_CTL
            0x28: 0x00,         # THRESH_FF
            0x29: 0x00,         # TIME_FF
            0x2A: 0x00,         # TAP_AXES
            0x2B: 0x00,         # ACT_TAP_STATUS
            0x2C: 0b0000_1010,  # BW_RATE
            0x2D: 0x00,         # POWER_CTL
            0x2E: 0x00,         # INT_ENABLE
            0x2F: 0x00,         # INT_MAP
            0x30: 0b0000_0010,  # INT_SOURCE
            0x31: 0x00,         # DATA_FORMAT
            0x32: 0x00,         # DATAX0
            0x33: 0x00,         # DATAX1
            0x34: 0x00,         # DATAY0
            0x35: 0x00,         # DATAY1
            0x36: 0x00,         # DATAZ0
            0x37: 0x00,         # DATAZ1
            0x38: 0x00,         # FIFO_CTL
            0x39: 0x00,         # FIFO_STATUS
        }
        super().__init__(bus)

    async def get_register(self, reg_num: int) -> int:
        await self.idle.wait()
        return self._registers[reg_num]

    def create_spi_command(self, operation: str, address: int, *, multibyte: bool = False) -> int:
        command = 0
        if operation == "read":
            command |= 1 << 7
        elif operation == "write":
            # it is already 0
            pass
        else:
            raise ValueError("Expected operation to bein ['read', 'write']")

        if address not in self._registers:
            raise ValueError(f"Expected address to be in {list(self._registers.keys())}")

        if multibyte:
            command |= 1 << 6

        return command | (address & 0x0f_ff)

    async def _transaction(self, frame_start, frame_end) -> None:
        await frame_start
        self.idle.clear()

        if not bool(self._sclk.value):
            raise SpiFrameError("ADXL345: sclk should be high at chip select edge")

        do_write = not bool(await self._shift(1))
        do_multibyte = bool(await self._shift(1))
        address = int(await self._shift(6))
        content = int(await self._shift(8, tx_word=self._registers[address]))

        if do_write:
            self._registers[address] = content

        if do_multibyte:
            # check for multibyte read/write by seeing which is first, a clk edge or frame end
            while await First(frame_end, FallingEdge(self._sclk)) != frame_end:
                address = address + 1
                self._miso.value = bool(self._registers[address] & 0b1000_0000)

                # shift in the remaining words
                rx_word = int(await self._shift(7, tx_word=(self._registers[address] & 0b0111_1111))) << 1

                # grab the last bit
                if (await First(RisingEdge(self._sclk), frame_end)) == frame_end or self._cs.value == 1:
                    raise SpiFrameError("End of frame in the middle of a transaction")
                rx_word |= int(self._mosi.value.integer)

                # perform write if necessary
                if do_write:
                    self._registers[address] = rx_word
        else:
            if await First(frame_end, FallingEdge(self._sclk)) != frame_end:
                raise SpiFrameError("ADXL345: received another clock edge when end of frame expected")

        if not bool(self._sclk.value):
            raise SpiFrameError("ADXL345: sclk should be high on chip select edge")
