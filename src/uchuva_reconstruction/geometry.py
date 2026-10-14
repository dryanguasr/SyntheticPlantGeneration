"""Small PLY helpers for analytical points; never silently convert splats."""
from pathlib import Path

import numpy as np


def read_colmap_points(path):
    """Read the binary little-endian XYZ/normal/RGB layout emitted by COLMAP."""
    with Path(path).open("rb") as stream:
        header = []
        while True:
            line = stream.readline()
            if not line:
                raise ValueError("Missing PLY header terminator")
            header.append(line.decode("ascii").strip())
            if line.strip() == b"end_header":
                break
        required = [f"property float {n}" for n in ("x", "y", "z", "nx", "ny", "nz")]
        required += [f"property uchar {n}" for n in ("red", "green", "blue")]
        properties = [line for line in header if line.startswith("property ")]
        if "format binary_little_endian 1.0" not in header or properties != required:
            raise ValueError("Expected COLMAP XYZ/normal/RGB PLY; Gaussian PLY is not supported")
        count = int(next(line.split()[2] for line in header if line.startswith("element vertex ")))
        dtype = [(n,"<f4") for n in ("x","y","z","nx","ny","nz")]
        dtype += [(n,"u1") for n in ("red","green","blue")]
        values = np.fromfile(stream, dtype=dtype, count=count)
        if len(values) != count:
            raise ValueError("Truncated PLY")
    return values


def write_colmap_points(path, values):
    header = ["ply", "format binary_little_endian 1.0", f"element vertex {len(values)}"]
    header += [f"property float {n}" for n in ("x","y","z","nx","ny","nz")]
    header += [f"property uchar {n}" for n in ("red","green","blue")]
    header += ["end_header"]
    with Path(path).open("wb") as stream:
        stream.write(("\n".join(header)+"\n").encode("ascii"))
        values.tofile(stream)
