#!/usr/bin/env python3
"""Servidor PTA concorrente de leitura de arquivos. Consulte --help."""

import argparse
import asyncio
from contextlib import suppress
import logging
from pathlib import Path
import signal

from protocol import InvalidRequest, MAX_REQUEST, parse_request, sequence_hint
from storage import FileStore, load_users

LOG = logging.getLogger("pta")
BASE = Path(__file__).resolve().parent
CHUNK_SIZE = 64 * 1024


class Session:
    def __init__(self, reader, writer, users, store, legacy_idle, framing="auto"):
        self.reader = reader
        self.writer = writer
        self.users = users
        self.store = store
        self.legacy_idle = legacy_idle
        self.authenticated = False
        self.closing = False
        self.busy = False
        self.operation = None
        self.framing = framing
        self.line_mode = framing == "lines"
        self.pending = bytearray()
        self.discarding = False

    async def reply(self, sequence: bytes, result: bytes):
        self.writer.write(sequence + b" " + result)
        await self.writer.drain()

    async def dispatch(self, frame: bytes):
        if self.busy or self.closing:
            return
        try:
            request = parse_request(frame)
        except InvalidRequest as error:
            await self.reply(error.sequence, b"NOK")
            self.closing = not self.authenticated
            return
        seq = request.sequence
        if not self.authenticated:
            if request.command == "CUMP" and request.argument in self.users:
                await self.reply(seq, b"OK")
                self.authenticated = True
            else:
                await self.reply(seq, b"NOK")
                self.closing = True
        elif request.command == "TERM":
            self.closing = True
            await self.reply(seq, b"OK")
        elif request.command in ("LIST", "PEGA"):
            self.busy = True
            self.operation = asyncio.create_task(self.perform(request))
        else:
            await self.reply(seq, b"NOK")

    async def perform(self, request):
        started = False
        try:
            if request.command == "LIST":
                names = self.store.list_files()
                payload = (f"ARQS {len(names)} " + ",".join(names)).encode("ascii")
                started = True
                await self.reply(request.sequence, payload)
            else:
                stream, size = self.store.open_file(request.argument)
                with stream:
                    started = True
                    await self.reply(request.sequence, f"ARQ {size} ".encode("ascii"))
                    remaining = size
                    while remaining:
                        data = stream.read(min(CHUNK_SIZE, remaining))
                        if not data:
                            raise OSError("arquivo truncado durante a transferência")
                        self.writer.write(data)
                        await self.writer.drain()
                        remaining -= len(data)
                        # drain() pode não ceder o controle se o socket estiver livre.
                        if remaining:
                            await asyncio.sleep(0)
        except (OSError, ValueError, UnicodeError) as error:
            LOG.debug("falha na operação: %s", error)
            if started:
                self.closing = True
                self.writer.close()
            else:
                try:
                    await self.reply(request.sequence, b"NOK")
                except (OSError, ConnectionError):
                    self.closing = True
                    self.writer.close()
        finally:
            self.busy = False

    async def oversized(self):
        await self.reply(sequence_hint(bytes(self.pending[:MAX_REQUEST])), b"NOK")
        self.closing = True

    async def receive(self, data: bytes):
        """Preserva o enquadramento mesmo ao descartar uma requisição ocupada."""
        segments = data.split(b"\n")
        for index, segment in enumerate(segments):
            terminated = index < len(segments) - 1
            if not segment and not terminated:
                continue
            if self.busy:
                self.discarding = True
                self.pending.clear()
            if not self.discarding:
                self.pending.extend(segment)
                # Reserva um CR extra: ele pode ser a primeira metade de CRLF.
                size = len(self.pending)
                if size > MAX_REQUEST and not (
                    size == MAX_REQUEST + 1 and self.pending.endswith(b"\r")
                ):
                    await self.oversized()
                    return
            if terminated:
                if self.framing == "auto":
                    self.line_mode = True
                if not self.discarding:
                    frame = bytes(self.pending)
                    if frame.endswith(b"\r"):
                        frame = frame[:-1]
                    if len(frame) > MAX_REQUEST:
                        await self.oversized()
                        return
                    await self.dispatch(frame)
                self.pending.clear()
                self.discarding = False
                if self.closing:
                    return

    async def legacy_boundary(self):
        """O silêncio delimita pedidos somente no modo compatível sem linhas."""
        if self.discarding:
            self.discarding = False
        elif len(self.pending) > MAX_REQUEST:
            await self.oversized()
        elif self.pending:
            await self.dispatch(bytes(self.pending))
        self.pending.clear()

    async def run(self):
        try:
            while not self.closing:
                try:
                    if (self.pending or self.discarding) and not self.line_mode:
                        data = await asyncio.wait_for(self.reader.read(CHUNK_SIZE), self.legacy_idle)
                    else:
                        data = await self.reader.read(CHUNK_SIZE)
                except asyncio.TimeoutError:
                    await self.legacy_boundary()
                    continue
                if not data:
                    if not self.line_mode:
                        await self.legacy_boundary()
                    if self.operation:
                        await self.operation
                    break
                await self.receive(data)
        except asyncio.CancelledError:
            # Um cliente lento não deve impedir o encerramento do processo.
            self.writer.transport.abort()
            raise
        except (OSError, ConnectionError):
            LOG.debug("cliente desconectado", exc_info=True)
        finally:
            if self.operation:
                if not self.operation.done():
                    self.operation.cancel()
                with suppress(asyncio.CancelledError, OSError):
                    await self.operation
            self.writer.close()
            with suppress(OSError):
                await self.writer.wait_closed()


async def serve(host, port, users, store, legacy_idle=0.1, framing="auto"):
    sessions = set()

    async def connected(reader, writer):
        task = asyncio.current_task()
        sessions.add(task)
        LOG.info("conexão aceita: %s", writer.get_extra_info("peername"))
        try:
            await Session(reader, writer, users, store, legacy_idle, framing).run()
        finally:
            sessions.discard(task)
            LOG.info("conexão encerrada: %s", writer.get_extra_info("peername"))

    server = await asyncio.start_server(connected, host, port)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopped.set)
            installed.append(sig)
        except NotImplementedError:
            pass
    try:
        LOG.info("PTA escutando em %s", ", ".join(str(s.getsockname()) for s in server.sockets))
        await stopped.wait()
    finally:
        server.close()
        active = list(sessions)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        # Python 3.13+ aguarda também os clientes: encerra as sessões primeiro.
        await server.wait_closed()
        for sig in installed:
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="endereço de escuta (padrão: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=11550, help="porta TCP (padrão: 11550)")
    parser.add_argument("--framing", choices=("auto", "lines", "legacy"), default="auto",
                        help="delimitação: auto detecta LF; lines exige LF; legacy usa silêncio")
    parser.add_argument("--legacy-idle-ms", type=float, default=100.0,
                        help="intervalo de silêncio sem LF (padrão: 100 ms)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("a porta deve estar entre 0 e 65535")
    if not 0 < args.legacy_idle_ms < float("inf"):
        parser.error("legacy-idle-ms deve ser finito e positivo")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        users = load_users(BASE / "users.txt")
        store = FileStore(BASE / "files")
        asyncio.run(serve(args.host, args.port, users, store,
                          args.legacy_idle_ms / 1000, args.framing))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Falha ao iniciar o PTA: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
