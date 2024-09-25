# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Spencer Chang
import logging
from abc import ABC
from abc import abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Deque
from typing import Iterable
from typing import Optional
from typing import Tuple

import cocotb
from cocotb.clock import BaseClock
from cocotb.triggers import Edge
from cocotb.triggers import Event
from cocotb.triggers import FallingEdge
from cocotb.triggers import First
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer
from cocotb_bus.bus import Bus

from .exceptions import SpiFrameError


class SpiBus(Bus):
    def __init__(self, entity=None, prefix=None, sclk_name='sclk', mosi_name='mosi', miso_name='miso', cs_name='cs', **kwargs):
        signals = {'sclk': sclk_name, 'mosi': mosi_name, 'miso': miso_name, 'cs': cs_name}
        super().__init__(entity, prefix, signals, **kwargs)

    @classmethod
    def from_entity(cls, entity, **kwargs):
        return cls(entity, **kwargs)

    @classmethod
    def from_prefix(cls, entity, prefix, **kwargs):
        return cls(entity, prefix, **kwargs)


@dataclass
class SpiConfig:
    word_width: int = 8
    sclk_freq: Optional[float] = 25e6
    cpol: bool = False
    cpha: bool = False
    msb_first: bool = True
    frame_spacing_ns: int = 1
    data_output_idle: int = 1
    ignore_rx_value: Optional[int] = None
    cs_active_low: bool = True


class SpiMaster:
    def __init__(self, bus: SpiBus, config: SpiConfig) -> None:
        self.log = logging.getLogger(f"cocotb.{bus.sclk._path}")

        # spi signals
        self._sclk = bus.sclk
        self._mosi = bus.mosi
        self._miso = bus.miso
        self._cs = bus.cs

        # size of a transfer
        self._config = config

        self.queue_tx: Deque[Tuple[int, bool]] = deque()
        self.queue_rx: Deque[int] = deque()

        self.sync = Event()

        self._idle = Event()
        self._idle.set()

        self._sclk.setimmediatevalue(int(self._config.cpol))
        self._mosi.setimmediatevalue(self._config.data_output_idle)
        self._cs.setimmediatevalue(1 if self._config.cs_active_low else 0)

        self._SpiClock = _SpiClock(
            signal=self._sclk,
            period=(1 / self._config.sclk_freq),
            units="sec",
            start_high=self._config.cpha,
        )

        self._run_coroutine_obj = None
        self._restart()

    def _restart(self) -> None:
        if self._run_coroutine_obj is not None:
            self._run_coroutine_obj.kill()
        self._run_coroutine_obj = cocotb.start_soon(self._run())

    async def write(self, data: Iterable[int], *, burst: bool = False):
        self.write_nowait(data, burst=burst)
        await self._idle.wait()

    def write_nowait(self, data: Iterable[int], *, burst: bool = False) -> None:
        """ Write the data to the MOSI line

        Args:
            data: an iterable of ints, if the wordwidth is 8, a bytearray is typically appropriate
            burst: if true, CS is not deasserted between writes
        """
        if self._config.msb_first:
            for b in data:
                self.queue_tx.append((int(b), burst))
        else:
            for b in data:
                self.queue_tx.append((reverse_word(int(b), self._config.word_width), burst))
        self.sync.set()
        self._idle.clear()

    async def read(self, count: int = -1):
        while self.empty_rx():
            self.sync.clear()
            await self.sync.wait()
        return self.read_nowait(count)

    def read_nowait(self, count: int = -1) -> Iterable[int]:
        if count < 0:
            count = len(self.queue_rx)
        if self._config.word_width == 8:
            data = bytearray()
        else:
            data = []
        for k in range(count):
            data.append(self.queue_rx.popleft())
        return data

    def count_tx(self) -> int:
        return len(self.queue_tx)

    def empty_tx(self) -> bool:
        return not self.queue_tx

    def count_rx(self) -> int:
        return len(self.queue_rx)

    def empty_rx(self) -> bool:
        return not self.queue_rx

    def idle(self) -> bool:
        return self.empty_tx() and self.empty_rx()

    def clear(self) -> None:
        """ Clears the RX and TX queues """
        self.queue_tx.clear()
        self.queue_rx.clear()

    async def wait(self) -> None:
        """ Wait for idle """
        await self._idle.wait()

    async def _run(self):
        while True:
            while not self.queue_tx:
                self._sclk.value = int(self._config.cpol)
                self._idle.set()
                self.sync.clear()
                await self.sync.wait()

            tx_word, burst = self.queue_tx.popleft()
            rx_word = 0

            self.log.debug("Write byte 0x%02x", tx_word)

            # the timing diagrams are CPHA/CPOL convention come from
            # https://en.wikipedia.org/wiki/Serial_Peripheral_Interface
            # this is also compliant with Linux Kernel definiton of SPI

            # if CPHA=0, the first bit is typically clocked out on edge of chip select
            if not self._config.cpha:
                self._mosi.value = bool(tx_word & (1 << self._config.word_width - 1))

            # set the chip select
            self._cs.value = int(not self._config.cs_active_low)
            await Timer(self._SpiClock.period, units='step')

            await self._SpiClock.start()

            if self._config.cpha:
                # if CPHA=1, the first edge is propagate, the second edge is sample
                for k in range(self._config.word_width):
                    # the out changes on the leading edge of clock
                    await Edge(self._sclk)
                    self._mosi.value = bool(tx_word & (1 << (self._config.word_width - 1 - k)))

                    # while the in captures on the trailing edge of the clock
                    await Edge(self._sclk)
                    rx_word |= bool(self._miso.value.integer) << (self._config.word_width - 1 - k)
            else:
                # if CPHA=0, the first edge is sample, the second edge is propagate
                # we already clocked out one bit on edge of chip select, so we will clock out less bits
                for k in range(self._config.word_width - 1):
                    await Edge(self._sclk)
                    rx_word |= bool(self._miso.value.integer) << (self._config.word_width - 1 - k)

                    await Edge(self._sclk)
                    self._mosi.value = bool(tx_word & (1 << (self._config.word_width - 2 - k)))

                # but we haven't sampled enough times, so we will wait for another edge to sample
                await Edge(self._sclk)
                rx_word |= bool(self._miso.value.integer)

            # set sclk back to idle state
            await self._SpiClock.stop()
            self._sclk.value = self._config.cpol

            # wait another sclk period before restoring the chip select and mosi to idle (not necessarily part of spec)
            await Timer(self._SpiClock.period, units='step')
            self._mosi.value = int(self._config.data_output_idle)
            if not burst or self.empty_tx():
                self._cs.value = int(self._config.cs_active_low)

            # wait some time before starting the next transaction
            await Timer(self._config.frame_spacing_ns, units='ns')

            if not self._config.msb_first:
                rx_word = reverse_word(rx_word, self._config.word_width)

            # if the ignore_rx_value has been set, ignore all rx_word equal to the set value
            if rx_word != self._config.ignore_rx_value:
                self.queue_rx.append(rx_word)

            self.sync.set()


class SpiSlaveBase(ABC):
    _config: SpiConfig

    def __init__(self, bus: SpiBus):
        self.log = logging.getLogger(f"cocotb.{bus.sclk._path}")

        self._sclk = bus.sclk
        self._mosi = bus.mosi
        self._miso = bus.miso
        self._cs = bus.cs

        self._miso.value = self._config.data_output_idle

        self.idle = Event()
        self.idle.set()

        self._run_coroutine_obj = None
        self._restart()

    def _restart(self):
        if self._run_coroutine_obj is not None:
            self._run_coroutine_obj.kill()
        self._run_coroutine_obj = cocotb.start_soon(self._run())

    async def _shift(self, num_bits: int, tx_word: Optional[int] = None) -> int:
        """ Shift in data on the MOSI signal. Shift out the tx_word on the MISO signal.

        Args:
            num_bits: the number of bits to shift
            tx_word: the word to be transmitted on the wire

        Returns:
            the received word on the MOSI line
        """
        rx_word = 0

        frame_end = RisingEdge(self._cs) if self._config.cs_active_low else FallingEdge(self._cs)

        for k in range(num_bits):
            # If both events happen at the same time, the returned one is indeterminate, thus
            # checking for cs = 1
            if (await First(Edge(self._sclk), frame_end)) == frame_end or self._cs.value == 1:
                raise SpiFrameError("End of frame in the middle of a transaction")

            if self._config.cpha:
                # when CPHA=1, the slave should shift out on the first edge
                if tx_word is not None:
                    self._miso.value = bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso.value = self._config.data_output_idle
            else:
                # when CPHA=0, the slave should sample on the first edge
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)

            # do the opposite of what was done on the first edge
            if (await First(Edge(self._sclk), frame_end)) == frame_end or self._cs.value == 1:
                raise SpiFrameError("End of frame in the middle of a transaction")

            if self._config.cpha:
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)
            else:
                if tx_word is not None:
                    self._miso.value = bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso.value = self._config.data_output_idle

        return rx_word

    async def _transparent_shift(self, num_bits: int, delay: int = 0, delay_units: str = 'ns') -> int:
        """ Shift in data on the MOSI signal, and present on MISO after a delay.

        As the data is shifted in from MOSI, present it back out on the MISO signal
        after a specified delay. This is equivalent to a fork in the flip flop output:
            MOSI > DFF |-> MISO
                       |-> RX_WORD_SHIFT_REGISTER


        Args:
            num_bits: the numbers of bits to transparently shift
            delay: the time to delay before copying MOSI to MISO (default=0)
            delay_units: the time units for the delay (default='ns')

        Returns:
            the received word on the MOSI line
        """
        rx_word = 0

        frame_end = RisingEdge(self._cs) if self._config.cs_active_low else FallingEdge(self._cs)
        propagate_out_delay = Timer(delay, units=delay_units)

        for k in range(num_bits):
            f = await First(Edge(self._sclk), frame_end)
            if not self._config.cpha:
                # when CPHA=0, the first thing the slave should do is read in
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)
                most_recent_bit = int(self._mosi.value.integer)

                w = await First(propagate_out_delay, frame_end, Edge(self._sclk))

                if w != propagate_out_delay:
                    if w == frame_end:
                        raise SpiFrameError("Unexpected end of frame in the middle of a transaction")
                    else:
                        raise SpiFrameError("Unexpected edge of sclk while waiting to propagate next bit")

                self._miso.value = bool(most_recent_bit)

            s = await First(Edge(self._sclk), frame_end)

            if self._config.cpha:
                # when CPHA=1, the second thing we should do is read in
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)
                most_recent_bit = int(self._mosi.value.integer)

                w = await First(propagate_out_delay, frame_end, Edge(self._sclk))

                if w != propagate_out_delay:
                    if w == frame_end:
                        raise SpiFrameError("Unexpected end of frame in the middle of a transaction")
                    else:
                        raise SpiFrameError("Unexpected edge of sclk while waiting to propagate next bit")

                self._miso.value = bool(most_recent_bit)

            if frame_end in (f, s):
                raise SpiFrameError("End of frame in the middle of a transaction")

        return rx_word

    @abstractmethod
    async def _transaction(self, frame_start, frame_end):
        """Implement the details of an SPI transaction """
        raise NotImplementedError("Please implement the _transaction method")

    async def _run(self):
        if self._config.cs_active_low:
            frame_start = FallingEdge(self._cs)
            frame_end = RisingEdge(self._cs)
        else:
            frame_start = RisingEdge(self._cs)
            frame_end = FallingEdge(self._cs)

        frame_spacing = Timer(self._config.frame_spacing_ns, units='ns')

        while True:
            self.idle.set()
            if (await First(frame_start, frame_spacing)) == frame_start:
                raise SpiFrameError(f"There must be at least {self._config.frame_spacing_ns} ns between frames")
            await self._transaction(frame_start, frame_end)


class _SpiClock(BaseClock):
    def __init__(self, signal, period, units="step", start_high=True):
        BaseClock.__init__(self, signal)
        self.period = cocotb.utils.get_sim_steps(period, units)
        self.half_period = cocotb.utils.get_sim_steps(period / 2.0, units)
        self.frequency = 1.0 / cocotb.utils.get_time_from_sim_steps(self.period, units='us')

        self.signal = signal

        self.start_high = start_high

        self._idle = Event()
        self._sync = Event()
        self._start = Event()

        self._idle.set()

        self._run_coroutine_obj = None
        self._restart()

    def _restart(self):
        if self._run_coroutine_obj is not None:
            self._run_cr.kill()
        self._run_cr = cocotb.start_soon(self._run())

    async def stop(self) -> None:
        self.stop_no_wait()
        await self._idle.wait()

    def stop_no_wait(self) -> None:
        self._start.clear()
        self._sync.set()

    async def start(self) -> None:
        self.start_no_wait()

    def start_no_wait(self) -> None:
        self._start.set()
        self._sync.set()

    async def _run(self):
        t = Timer(self.half_period)
        if self.start_high:
            while True:
                while not self._start.is_set():
                    self._idle.set()
                    self._sync.clear()
                    await self._sync.wait()

                self._idle.clear()
                self.signal.value = 1
                await t
                if self._start.is_set():
                    self.signal.value = 0
                    await t
        else:
            while True:
                while not self._start.is_set():
                    self._idle.set()
                    self._sync.clear()
                    await self._sync.wait()

                self._idle.clear()
                self.signal.value = 0
                await t
                if self._start.is_set():
                    self.signal.value = 1
                    await t


def reverse_word(n: int, width: int) -> int:
    return int('{:0{width}b}'.format(n, width=width)[::-1], 2)
