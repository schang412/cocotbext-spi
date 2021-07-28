
import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, First, Timer, Event
from ... import SpiSlaveBase, SpiConfig, SpiFrameError, SpiFrameTimeout


class DRV8304(SpiSlaveBase):
    def __init__(self, signals):
        self._config = SpiConfig(
            word_width=16,
            cpol=False,
            cpha=True,
            msb_first=True
        )

        self._registers = {
            0: 0b00000000000,
            1: 0b00000000000,
            2: 0b00000000000,
            3: 0b01101110111,
            4: 0b11101110111,
            5: 0b00101000101,
            6: 0b01010000011
        }

        self._idle = Event()
        self._idle.set()

        super().__init__(signals)

    async def get_register(self, reg_num):
        await self._idle.wait()
        return self._registers[reg_num]

    def create_spi_word(self, operation, address, content):
        command = 0
        if operation == "read":
            command |= 1 << 15
        elif operation == "write":
            # it is already 0
            pass
        else:
            raise ValueError("Expected operation to be in ['read', 'write']")

        try:
            self._registers[address]
        except KeyError:
            raise ValueError(f"Expected address to be in {list(self._registers.keys())}")
        command |= (address & 0b1111) << 11
        command |= (content & 0b11111111111)

        return command

    async def _run(self):
        if self._cs_active_low:
            frame_start = FallingEdge(self._cs)
            frame_end = RisingEdge(self._cs)
        else:
            frame_start = RisingEdge(self._cs)
            frame_end = FallingEdge(self._cs)

        frame_spacing = Timer(400, units="ns")

        while True:
            # start of frame
            self._idle.set()
            if (await First(frame_start, frame_spacing)) == frame_start:
                raise SpiFrameError("DRV8304: nSCS should be pulled high for at least 400ns between words")
            await frame_start
            self._idle.clear()

            # SCLK pin should be low at the chip select edge
            if bool(self._sclk.value):
                raise SpiFrameError("DRV8304: sclk should be low at chip select edge")

            do_write = not bool(await self._shift(1))
            address = int(await self._shift(4))
            content = int(await self._shift(11, tx_word=self._registers[address]))

            # end of frame
            if await First(frame_end, RisingEdge(self._sclk)) != frame_end:
                raise SpiFrameError("DRV8304: clocked more than 16 bits")

            if bool(self._sclk.value):
                raise SpiFrameError("DRV8304: sclk should be low at chip select edge")

            if do_write:
                self._registers[address] = content
