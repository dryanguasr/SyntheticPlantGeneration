"""Preserve workbook cells and sample observed ArUco corners, without metric assumptions."""
from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import cv2
import numpy as np
from prepare_union_pilot import ROOT, sha, write

VIDEOS = [Path(f'C:/Users/User/Downloads/{name}.mp4') for name in ('125180','125181','125182')]
WORKBOOK = Path('C:/Users/User/Downloads/uchuvas.xlsx')


def image_relative_xy(point, marker_center):
    """Image offsets: X right, Y up. No assertion of physical coordinates."""
    return [float(point[0]-marker_center[0]), float(marker_center[1]-point[1])]


def camera_displacement_to_user_cm(vector_m):
    """Convention fixture only: camera right/down/forward to right/up/inward.

    This reflects one axis (determinant -1), not an SO(3) pose rotation.
    It converts a displacement, never establishes an unknown physical origin.
    No measured video coordinates are passed through this uncalibrated contract.
    """
    if vector_m is None:
        return None
    vector = np.asarray(vector_m, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError('A finite 3D displacement in meters is required')
    return (vector * np.array([100., -100., 100.])).tolist()


def manual_references(sheet):
    """Parse the explicit N:Q block; keep absent coordinates unknown."""
    references = []
    marker, ordinal, current = None, 0, None
    for row in range(4, 100):
        if sheet.get(f'N{row}'):
            marker = sheet[f'N{row}']; ordinal = 0
        axis = sheet.get(f'P{row}', '').lower()
        if axis == 'x':
            ordinal += 1
            current = {'marker_label': marker, 'ordinal_within_marker': ordinal,
                       'coordinates_cm': {}, 'cells': {}, 'fruit_identity_verified': False,
                       'video_association': None, 'origin_verified': False}
            references.append(current)
        if current is not None and axis in ('x', 'y', 'z'):
            raw = sheet.get(f'Q{row}')
            try:
                value = float(raw) if raw not in (None, '') else None
            except (ValueError, TypeError):
                value = None
            current['coordinates_cm'][axis] = value
            current['cells'][axis] = f'Hoja 2!Q{row}'
    return references


def workbook_cells(path):
    ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(t.text or '' for t in s.iter('{'+ns['m']+'}t'))
                   for s in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = list(workbook.find('m:sheets',ns))
        rels = {r.get('Id'):r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        result = []
        for sheet in sheets:
            target = rels[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            target = target.lstrip('/') if target.startswith('/') else 'xl/'+target
            cells = []
            for cell in ET.fromstring(archive.read(target)).findall('.//m:sheetData/m:row/m:c',ns):
                v, f = cell.find('m:v',ns), cell.find('m:f',ns)
                value = v.text if v is not None else ''.join(t.text or '' for t in cell.findall('.//m:t',ns))
                if cell.get('t') == 's' and value:
                    value = strings[int(value)]
                if value or f is not None:
                    cells.append({'cell':cell.get('r'),'value':value,'formula':f.text if f is not None else None,
                                  'missing_detection':str(value).strip().lower().replace(' ','') == 'nodetecta'})
            result.append({'sheet':sheet.get('name'),'cells':cells})
        return result


def main():
    output = ROOT/'references'
    output.mkdir(exist_ok=True)
    cells = workbook_cells(WORKBOOK)
    write(output/'workbook_cells.json', {'source':str(WORKBOOK),'sha256':sha(WORKBOOK),'units':'cm, user confirmed',
          'axes':'X right, Y up, Z inward','origin':None,'data':cells,
          'historical_M0_M1_are_not_new_model_predictions':True,'cached_precision_formulas_not_used_as_metrics':True})
    sheet = {c['cell']:c['value'] for s in cells if s['sheet']=='Hoja 2' for c in s['cells']}
    references = manual_references(sheet)
    write(output/'manual_marker_references.json', references)
    cv2.setNumThreads(2)
    detector_parameters = cv2.aruco.DetectorParameters()
    detector_parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), detector_parameters)
    summaries = []
    for path in VIDEOS:
        cap = cv2.VideoCapture(str(path))
        fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        targets = {round(k*fps/5) for k in range(int(np.ceil(count/fps*5))) if round(k*fps/5)<count}
        records, ids_seen, first_saved = [], Counter(), set()
        frame_index = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if frame_index in targets:
                ok, image = cap.retrieve()
                if not ok:
                    raise ValueError('Frame decode failed')
                corners, ids, rejected = detector.detectMarkers(image)
                markers = []
                if ids is not None:
                    for corner, marker_id in zip(corners, ids.ravel()):
                        pts = corner.reshape(4,2)
                        marker_id = int(marker_id)
                        ids_seen[marker_id] += 1
                        markers.append({'id':marker_id,'corners_px':pts.tolist(),'center_px':pts.mean(0).tolist(),
                                        'mean_side_px':float(np.linalg.norm(pts-np.roll(pts,1,axis=0),axis=1).mean())})
                        if marker_id not in first_saved:
                            first_saved.add(marker_id)
                            preview = image.copy()
                            cv2.aruco.drawDetectedMarkers(preview, [corner], np.array([[marker_id]]))
                            cv2.imwrite(str(output/f'{path.stem}_marker_{marker_id}.jpg'), preview)
                records.append({'frame_index':frame_index,'timestamp_seconds':frame_index/fps,'markers':markers,
                                'pose_status':'unavailable_missing_intrinsics_and_marker_side','metric_xyz':None})
            frame_index += 1
        cap.release()
        write(output/f'{path.stem}_aruco.json', records)
        summaries.append({'path':str(path),'sha256':sha(path),'frames':count,'fps':fps,'sampled_frames':len(records),
                          'frames_with_marker':sum(bool(r['markers']) for r in records),'ids_frame_counts':dict(ids_seen),
                          'dictionary':'DICT_4X4_50','origin_verified':False,'metric_pose_available':False})
        print(json.dumps(summaries[-1]), flush=True)
    write(output/'video_reference_summary.json', summaries)


if __name__ == '__main__':
    main()
