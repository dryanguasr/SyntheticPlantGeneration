"""Plot a sparse COLMAP component and its recovered camera trajectory."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    points = []
    colors = []
    errors = []
    lengths = []
    for line in (args.model / "points3D.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        points.append([float(x) for x in fields[1:4]])
        colors.append([int(x)/255 for x in fields[4:7]])
        errors.append(float(fields[7]))
        lengths.append((len(fields)-8)//2)
    xyz = np.asarray(points)
    colors = np.asarray(colors)
    poses = json.loads((args.model / "poses.json").read_text())["images"]
    poses.sort(key=lambda r:r["image"])
    rotate = np.array([[1,0,0],[0,0,1],[0,-1,0]]) @ np.asarray(poses[0]["cam_from_world"])[:,:3]
    center = np.median(xyz, axis=0)
    xyz = (xyz-center) @ rotate.T
    cameras = (np.asarray([p["center"] for p in poses])-center) @ rotate.T
    limits = np.quantile(xyz, [.01,.99], axis=0)
    fig, axes = plt.subplots(1,3,figsize=(16,5))
    for ax, (a,b), title in zip(axes, [(0,2),(0,1),(1,2)], ["Frente", "Planta", "Perfil"]):
        ax.scatter(xyz[:,a],xyz[:,b],c=colors,s=.7,rasterized=True)
        ax.plot(cameras[:,a],cameras[:,b],"r.-",lw=.8,ms=2,label="Cámaras recuperadas")
        lo=np.minimum(limits[0],cameras.min(axis=0));hi=np.maximum(limits[1],cameras.max(axis=0))
        ax.set_xlim(lo[a],hi[a]);ax.set_ylim(lo[b],hi[b]);ax.set_aspect("equal")
        ax.set_title(title);ax.set_xlabel("Unidades arbitrarias");ax.grid(alpha=.15)
    axes[0].legend(fontsize=8)
    fig.suptitle("Nube dispersa y trayectoria local: orientación de la primera cámara, sin escala física\nVentana de visualización 1–99 % de puntos; nube original conservada")
    fig.tight_layout();args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=150);plt.close(fig)
    print(json.dumps(dict(points=len(points),cameras=len(poses),median_track=float(np.median(lengths)),
        error_quantiles=np.quantile(errors,[.5,.9,.99]).tolist(),window_01_99_arbitrary=limits.tolist())))


if __name__ == "__main__":
    main()
