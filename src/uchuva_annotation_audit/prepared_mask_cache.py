"""Lossless cache for PrivateDataset's unaugmented training projections."""

from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

import cv2
import numpy as np

from .store import SessionLock, atomic_json, read, sha


VERSION = 'private-native-mask-projection-cache/1'
FIELDS = {'binding', 'rgb', 'masks', 'classes', 'boxes', 'ignored'}


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def projection_protocol(size, ratio):
    """Identify all inputs to the frozen RGB and native-mask projection."""
    if type(size) is not int or type(ratio) is not int or ratio < 1 or size < 32 or size % 32 or size % ratio:
        raise ValueError('Unsupported private projection grid')
    here = Path(__file__).resolve().parent
    sources = {name: sha(here / name) for name in ('private_training.py', 'masks.py', 'store.py', Path(__file__).name)}
    software = {name: version(name) for name in ('numpy', 'Pillow', 'torch', 'ultralytics')}
    software.update(python=platform.python_version(), machine=platform.machine(), byte_order=sys.byteorder,
                    opencv=cv2.__version__, opencv_build=digest(cv2.getBuildInformation()),
                    opencv_cpu_features=cv2.getCPUFeaturesLine(), opencv_threads=cv2.getNumThreads(),
                    opencv_optimized=cv2.useOptimized(), opencv_ipp=cv2.ipp.useIPP(),
                    opencv_ipp_inexact=cv2.ipp.useIPP_NotExact())
    return dict(version=VERSION, size=size, ratio=ratio, sources=sources, software=software)


def input_binding(row, protocol_key):
    """Use the existing sealed bytes and do not cache an unbound photo or annotation."""
    for field in ('image', 'annotation'):
        if sha(row[field]) != row[f'{field}_sha256']:
            raise ValueError(f'Frozen {field} changed: {row["id"]}')
    if any(type(row[axis]) is not int or row[axis] <= 0 for axis in ('width', 'height')):
        raise ValueError(f'Invalid frozen dimensions: {row["id"]}')
    return dict(id=row['id'], image_sha256=row['image_sha256'], annotation_sha256=row['annotation_sha256'],
                width=row['width'], height=row['height'], protocol_key=protocol_key)


def checked_projection(value, size, grid):
    canvas, masks, classes, boxes, ignored = value
    count = classes.size
    if (canvas.shape != (size, size, 3) or canvas.dtype != np.uint8
            or classes.shape != (count,) or classes.dtype != np.int64
            or masks.shape != (count, grid, grid) or masks.dtype != np.bool_
            or boxes.shape != (count, 4) or boxes.dtype != np.float32
            or ignored.shape != (grid, grid) or ignored.dtype != np.bool_):
        raise ValueError('Cached projection differs from the shape or dtype contract of PrivateDataset')
    return value


def write_projection(path, value, binding, size, grid):
    canvas, masks, classes, boxes, ignored = checked_projection(value, size, grid)
    fd, pending = tempfile.mkstemp(prefix='.projection-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            np.savez(stream, binding=np.frombuffer(json_bytes(binding), dtype=np.uint8),
                     rgb=np.ascontiguousarray(canvas[:, :, ::-1]), classes=classes, boxes=boxes,
                     masks=np.packbits(masks, axis=-1, bitorder='little'),
                     ignored=np.packbits(ignored, axis=-1, bitorder='little'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        Path(pending).unlink(missing_ok=True)


def fingerprint(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@dataclass(frozen=True, slots=True)
class Entry:
    path: Path
    binding: dict
    sha256: str
    fingerprint: tuple


class PreparedMaskCache:
    """Content-addressed, reusable projections for already sealed training rows."""

    def __init__(self, root, *, size=960, ratio=4):
        self.size = size
        self.ratio = ratio
        self.protocol = projection_protocol(size, ratio)
        self.grid = size // ratio
        self.protocol_key = digest(self.protocol)
        self.root = Path(root).resolve() / 'prepared_mask_cache' / self.protocol_key[:24]

    def describe(self, binding):
        # Full digests remain in the protocol, receipts and NPZ. Short file
        # names keep Windows under its path limit on ordinary workspaces.
        name = digest(binding)[:32]
        return self.root / f'{name}.npz', self.root / f'{name}.json'

    def check_protocol(self):
        current = projection_protocol(self.size, self.ratio)
        if current != self.protocol or read(self.root / 'protocol.json') != current:
            raise ValueError('The projection source or environment differs from its cache protocol')

    def _entry(self, binding):
        projection, receipt = self.describe(binding)
        stamp = read(receipt)
        before = fingerprint(projection)
        if (stamp['binding'] != binding or stamp['bytes'] != before[0] or sha(projection) != stamp['sha256']
                or fingerprint(projection) != before):
            raise ValueError(f'Cached projection differs from the sealed receipt: {binding["id"]}')
        return Entry(projection, binding, stamp['sha256'], before)

    def preflight(self, rows):
        self.check_protocol()
        return [self._entry(input_binding(row, self.protocol_key)) for row in rows]

    def build(self, dataset):
        """Call the unchanged frozen projection on the CPU once per missing row."""
        self._check_dataset(dataset)
        self.root.mkdir(parents=True, exist_ok=True)
        protocol_path = self.root / 'protocol.json'
        created = 0
        with closing(SessionLock(self.root / 'writer.lock')):
            if not protocol_path.exists():
                atomic_json(protocol_path, self.protocol, exclusive=True)
            self.check_protocol()
            for index, row in enumerate(dataset.rows):
                binding = input_binding(row, self.protocol_key)
                projection, receipt = self.describe(binding)
                if receipt.exists():
                    self._entry(binding)
                    continue
                value = dataset._prepare(index)
                if input_binding(row, self.protocol_key) != binding:
                    raise ValueError(f'Frozen input changed while preparing {row["id"]}')
                write_projection(projection, value, binding, self.size, self.grid)
                atomic_json(receipt, dict(binding=binding, sha256=sha(projection), bytes=projection.stat().st_size),
                            exclusive=True)
                created += 1
        return created

    def load(self, entry):
        if fingerprint(entry.path) != entry.fingerprint:
            raise ValueError(f'Cached projection changed after preflight: {entry.binding["id"]}')
        with np.load(entry.path, allow_pickle=False) as archive:
            if set(archive.files) != FIELDS or archive['binding'].tobytes() != json_bytes(entry.binding):
                raise ValueError(f'Unexpected cache archive binding: {entry.binding["id"]}')
            rgb, classes, boxes = (archive[key] for key in ('rgb', 'classes', 'boxes'))
            masks, ignored = (archive[key] for key in ('masks', 'ignored'))
        packed_width = (self.grid + 7) // 8
        if (rgb.dtype != np.uint8 or rgb.shape != (self.size, self.size, 3)
                or masks.dtype != np.uint8 or masks.shape != (classes.size, self.grid, packed_width)
                or ignored.dtype != np.uint8 or ignored.shape != (self.grid, packed_width)):
            raise ValueError(f'Unexpected packed mask dimensions: {entry.binding["id"]}')
        canvas = np.ascontiguousarray(rgb[:, :, ::-1])
        binary = np.unpackbits(masks, count=self.grid, axis=-1, bitorder='little').view(np.bool_)
        ignore_grid = np.unpackbits(ignored, count=self.grid, axis=-1, bitorder='little').view(np.bool_)
        if fingerprint(entry.path) != entry.fingerprint:
            raise ValueError(f'Cached projection changed while reading: {entry.binding["id"]}')
        return checked_projection((canvas, binary, classes, boxes, ignore_grid), self.size, self.grid)

    def _check_dataset(self, dataset):
        from .private_training import PrivateDataset

        if dataset.size != self.size or dataset.ratio != self.ratio:
            raise ValueError('The cached grid does not match the training dataset')
        if not isinstance(dataset, PrivateDataset) or dataset._prepare.__func__ is not PrivateDataset._prepare:
            raise ValueError('The cache requires the frozen PrivateDataset projection')

    def bind(self, dataset):
        """Replace only this dataset's unaugmented lookup. Order and slot RNG stay in the trainer."""
        self._check_dataset(dataset)
        entries = self.preflight(dataset.rows)
        dataset.original = lru_cache(maxsize=24)(lambda index: self.load(entries[index]))
        return dict(protocol_key=self.protocol_key,
                    entries_sha256=digest([(entry.binding, entry.sha256) for entry in entries]), rows=len(entries))
