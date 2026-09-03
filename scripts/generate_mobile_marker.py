"""Produce a verified ArUco ID 0 and an A4 printable SVG/HTML with a 100 mm marker."""
from pathlib import Path
import json
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = ROOT / "outputs/mobile/marker"
    output.mkdir(parents=True, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    pixels = cv2.aruco.generateImageMarker(dictionary, 0, 600)
    padded = cv2.copyMakeBorder(pixels, 100, 100, 100, 100, cv2.BORDER_CONSTANT, value=255)
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(padded)
    assert ids is not None and ids.flatten().tolist() == [0]
    rects = []
    for row in range(6):
        for col in range(6):
            if pixels[row * 100 + 50, col * 100 + 50] == 0:
                rects.append(f'<rect x="{55 + col * 100 / 6:.8f}" y="{75 + row * 100 / 6:.8f}" width="{100 / 6:.8f}" height="{100 / 6:.8f}"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">
<rect width="210" height="297" fill="white"/>
<g font-family="sans-serif" text-anchor="middle" fill="#17271d">
<text x="105" y="25" font-size="8">UCHUVA / ArUco</text>
<text x="105" y="36" font-size="4">DICT_4X4_50 · ID 0</text>
<text x="105" y="47" font-size="4">Lado negro exterior: 100 mm (10 cm)</text>
</g><g fill="black" shape-rendering="crispEdges">{''.join(rects)}</g>
<g font-family="sans-serif" text-anchor="middle" fill="#17271d" font-size="4">
<text x="105" y="205">Imprimir en A4 al 100 %, sin ajustar a página.</text>
<text x="105" y="216">Medir el lado negro con una regla después de imprimir.</text>
<text x="105" y="227">Confirmar esa medida en Ajustes de la aplicación.</text>
<text x="105" y="246">Montar sobre una superficie plana y rígida.</text>
<text x="105" y="257">Mantener el margen blanco libre de objetos.</text>
</g></svg>'''
    (output / "aruco_4x4_50_id0_100mm.svg").write_text(svg, encoding="utf-8")
    html = '<!doctype html><html lang="es"><meta charset="utf-8"><title>ArUco ID 0 · 10 cm</title><style>@page{size:A4;margin:0}body{margin:0;background:white}svg{display:block;width:210mm;height:297mm}</style>' + svg + '</html>'
    (output / "imprimir_aruco.html").write_text(html, encoding="utf-8")
    cv2.imwrite(str(output / "marker_preview.png"), padded)
    (output / "verification.json").write_text(json.dumps({"dictionary": "DICT_4X4_50", "id": 0, "black_side_mm": 100,
        "verified_decode": ids.flatten().tolist(), "corners_px": np.asarray(corners).tolist(), "print_scale_must_be_measured": True}, indent=2))
    print(output)


if __name__ == "__main__":
    main()
