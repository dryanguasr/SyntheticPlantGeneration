"""Estimación local del desfase WSL menos Windows, sin ajustar el reloj."""

from queue import Empty, Queue
from contextlib import contextmanager
from statistics import median
import subprocess
from threading import Event, Thread
import time


@contextmanager
def clock_probe(distro):
    script = "import sys,time\nfor _ in sys.stdin: print(time.monotonic_ns(), flush=True)"
    with subprocess.Popen(
        ["wsl.exe", "-d", distro, "--", "python3", "-u", "-c", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as child:
        replies = Queue()

        def read():
            for line in child.stdout:
                replies.put((time.monotonic_ns(), line))
            replies.put((0, ""))

        Thread(target=read, daemon=True).start()
        def measure(warm=False):
            samples = []
            try:
                for index in range(7):
                    before = time.monotonic_ns()
                    child.stdin.write("\n")
                    child.stdin.flush()
                    after, response = replies.get(timeout=12 if not warm and index == 0 else 2)
                    stamp = int(response)
                    if (warm or index) and 0 <= after - before <= 20_000_000:
                        samples.append(stamp - (before + after) // 2)
                        if warm and len(samples) >= 3:
                            recent = samples[-3:]
                            if max(recent) - min(recent) <= 20_000_000:
                                return int(median(recent))
            except (Empty, OSError, ValueError) as error:
                raise RuntimeError("No se pudo medir el reloj de WSL.") from error
            if len(samples) < 3 or max(samples) - min(samples) > 20_000_000:
                raise RuntimeError("Medición de relojes inestable. Reintenta al iniciar WSL.")
            return int(median(samples))

        try:
            yield measure
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()


def clock_offset_ns(distro):
    with clock_probe(distro) as measure:
        return measure()


class CameraClock:
    """Mantiene disponible la vista mientras se recupera la referencia ROS."""

    def __init__(self, distro, report):
        self.distro, self.report = distro, report
        self.snapshot = (None, 0.0)
        self.closed = Event()

    def __enter__(self):
        Thread(target=self.refresh, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.closed.set()

    def offset(self):
        value, measured = self.snapshot
        return value if time.monotonic() - measured < 30 else None

    def refresh(self):
        self.report("Sincronizando reloj WSL. El vídeo local está disponible.")
        while not self.closed.is_set():
            previous = self.offset()
            try:
                offset = clock_offset_ns(self.distro)
            except (RuntimeError, OSError):
                if previous is None:
                    self.report("WSL aún no responde al reloj. Reintentando; XYZ ROS en espera.")
                self.closed.wait(2)
                continue
            if self.closed.is_set():
                break
            self.snapshot = (offset, time.monotonic())
            if previous is None or abs(offset - previous) > 30_000_000:
                self.report(f"Reloj WSL compensado: {offset / 1e6:+.0f} ms.")
            self.closed.wait(12)
