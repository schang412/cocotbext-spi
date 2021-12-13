"""
Copyright (c) 2021 Spencer Chang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import logging
from collections import deque, namedtuple
from typing import Optional

import cocotb
from cocotb.triggers import Timer, Event, First, RisingEdge, FallingEdge
from cocotb.clock import BaseClock

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .about import __version__


@dataclass
class SpiSignals:
    # cocotb.handle.ModifiableObject is the handle for a signal
    sclk: cocotb.handle.ModifiableObject
    mosi: cocotb.handle.ModifiableObject
    miso: cocotb.handle.ModifiableObject
    cs: cocotb.handle.ModifiableObject
    cs_active_low: bool = True


@dataclass
class SpiConfig:
    word_width: int = 8
    sclk_freq: Optional[float] = 25e6
    cpol: bool = False
    cpha: bool = False
    msb_first: bool = True
    frame_spacing_ns: int = 1
    data_output_idle: int = 1


class SpiFrameError(Exception):
    pass


class SpiFrameTimeout(Exception):
    pass


class SpiMaster:
    def __init__(self, signals, config):
        self.log = logging.getLogger(f"cocotb.{signals.sclk._path}")

        # spi signals
        self._sclk = signals.sclk
        self._mosi = signals.mosi
        self._miso = signals.miso
        self._cs = signals.cs
        self._cs_active_low = signals.cs_active_low

        # size of a transfer
        self._config = config

        self.queue_tx = deque()
        self.queue_rx = deque()

        self.sync = Event()

        self._idle = Event()
        self._idle.set()

        self._sclk.setimmediatevalue(int(self._config.cpol))
        self._mosi.setimmediatevalue(self._config.data_output_idle)
        self._cs.setimmediatevalue((1 if self._cs_active_low else 0))

        self._SpiClock = _SpiClock(signal=self._sclk,
                                   period=(1 / self._config.sclk_freq),
                                   units="sec",
                                   start_high=self._config.cpha)

        self._run_coroutine_obj = None
        self._restart()

    def _restart(self):
        if self._run_coroutine_obj is not None:
            self._run_coroutine_obj.kill()
        self._run_coroutine_obj = cocotb.fork(self._run())

    async def write(self, data):
        self.write_nowait(data)
        await self._idle.wait()

    def write_nowait(self, data):
        if self._config.msb_first:
            for b in data:
                self.queue_tx.append(int(b))
        else:
            for b in data:
                self.queue_tx.append(reverse_word(int(b), self._config.word_width))
        self.sync.set()
        self._idle.clear()

    async def read(self, count=-1):
        while self.empty_rx():
            self.sync.clear()
            await self.sync.wait()
        return self.read_nowait(count)

    def read_nowait(self, count=-1):
        if count < 0:
            count = len(self.queue_rx)
        if self._config.word_width == 8:
            data = bytearray()
        else:
            data = []
        for k in range(count):
            data.append(self.queue_rx.popleft())
        return data

    def count_tx(self):
        return len(self.queue_rx)

    def empty_tx(self):
        return not self.queue_tx

    def count_rx(self):
        return len(self.queue_rx)

    def empty_rx(self):
        return not self.queue_rx

    def idle(self):
        return self.empty_tx() and self.empty_rx()

    def clear(self):
        self.queue_tx.clear()
        self.queue_rx.clear()

    async def wait(self):
        await self._idle.wait()

    async def _run(self):
        while True:
            while not self.queue_tx:
                self._sclk <= int(self._config.cpol)
                self._idle.set()
                self.sync.clear()
                await self.sync.wait()

            tx_word = self.queue_tx.popleft()
            rx_word = 0

            self.log.debug("Write byte 0x%02x", tx_word)

            # set the chip select
            self._cs <= int(not self._cs_active_low)
            await Timer(self._SpiClock.period, units='step')

            # if CPHA=0, the first bit is typically clocked out on edge of chip select
            if not self._config.cpha:
                self._mosi <= bool(tx_word & (1 << self._config.word_width - 1))

            await self._SpiClock.start()

            # The SPI mode timing diagrams are from:
            # https://www.analog.com/en/analog-dialogue/articles/introduction-to-spi-interface.html
            # Note that the first edge we see is always a rising edge
            if self._config.cpha:
                # if CPHA=1, the rising edge is propagate, the falling edge is sample
                for k in range(self._config.word_width):
                    await RisingEdge(self._sclk)
                    self._mosi <= bool(tx_word & (1 << (self._config.word_width - 1 - k)))
                    await FallingEdge(self._sclk)
                    rx_word |= bool(self._miso.value.integer) << (self._config.word_width - 1 - k)
            else:
                # if CPHA=0, the rising edge is sample, the falling edge is propagate
                # we already clocked out one bit on edge of chip select, so we will clock out less bits
                for k in range(self._config.word_width - 1):
                    await RisingEdge(self._sclk)
                    rx_word |= bool(self._miso.value.integer) << (self._config.word_width - 1 - k)
                    await FallingEdge(self._sclk)
                    self._mosi <= bool(tx_word & (1 << (self._config.word_width - 2 - k)))
                # but we haven't sampled enough times, so we will wait for another rising edge to sample
                await RisingEdge(self._sclk)
                rx_word |= bool(self._miso.value.integer)

                # at this point, we should have shifted out all the bits, if our clock is normally low,
                # we will see one more falling edge before the chip select, we should put the idle value
                # on the line when we see that last falling edge.
                if not self._config.cpol:
                    await FallingEdge(self._sclk)
                    self._mosi <= self._config.data_output_idle

            # set sclk back to idle state
            await self._SpiClock.stop()
            self._sclk <= self._config.cpol

            # wait another sclk period before restoring the chip select and mosi to idle (not necessarily part of spec)
            await Timer(self._SpiClock.period, units='step')
            self._cs <= int(self._cs_active_low)
            self._mosi <= int(self._config.data_output_idle)

            # wait some time before starting the next transaction
            await Timer(self._config.frame_spacing_ns, units='ns')

            if not self._config.msb_first:
                rx_word = reverse_word(rx_word, self._config.word_width)

            self.queue_rx.append(rx_word)
            self.sync.set()


class SpiSlaveBase(ABC):
    def __init__(self, signals):
        self.log = logging.getLogger(f"cocotb.{signals.sclk._path}")

        self._sclk = signals.sclk
        self._mosi = signals.mosi
        self._miso = signals.miso
        self._cs = signals.cs
        self._cs_active_low = signals.cs_active_low

        self._miso <= self._config.data_output_idle

        self.idle = Event()
        self.idle.set()

        self._run_coroutine_obj = None
        self._restart()

    def _restart(self):
        if self._run_coroutine_obj is not None:
            self._run_coroutine_obj.kill()
        self._run_coroutine_obj = cocotb.fork(self._run())

    async def _shift(self, num_bits, tx_word=None):
        rx_word = 0

        for k in range(num_bits):
            await RisingEdge(self._sclk)
            if self._config.cpha:
                # when CPHA=1, the slave should shift out on a rising edge
                if tx_word is not None:
                    self._miso <= bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso <= self._config.data_output_idle
            else:
                # when CPHA=0, the slave should sample on a rising edge
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)

            # do the opposite of what was done on the rising edge
            await FallingEdge(self._sclk)
            if self._config.cpha:
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)
            else:
                if tx_word is not None:
                    self._miso <= bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso <= self._config.data_output_idle

        return rx_word

    @abstractmethod
    async def _transaction(self, frame_start, frame_end):
        """Implement the details of an SPI transaction """
        raise NotImplementedError("Please implement the _transaction method")

    async def _run(self):
        if self._cs_active_low:
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
        self._run_cr = cocotb.fork(self._run())

    async def stop(self):
        self.stop_no_wait()
        await self._idle.wait()

    def stop_no_wait(self):
        self._start.clear()
        self._sync.set()

    async def start(self):
        self.start_no_wait()

    def start_no_wait(self):
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
                self.signal <= 1
                await t
                if self._start.is_set():
                    self.signal <= 0
                    await t
        else:
            while True:
                while not self._start.is_set():
                    self._idle.set()
                    self._sync.clear()
                    await self._sync.wait()

                self._idle.clear()
                self.signal <= 0
                await t
                if self._start.is_set():
                    self.signal <= 1
                    await t


def reverse_word(n, width):
    return int('{:0{width}b}'.format(n, width=width)[::-1], 2)
