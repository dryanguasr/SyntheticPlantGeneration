import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('binary_context',ROOT/'scripts/binary_segmentation_context.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class BinaryContextTests(unittest.TestCase):
    def test_binary_header_positions_normals_and_uv_convention(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.obj';target=Path(directory)/'target.glb'
            source.write_text('v 1 2 3\nv 2 2 3\nv 1 3 3\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 0 1\nf 1/1/1 2/2/1 3/3/1\n')
            report=module.convert(source,target);payload=target.read_bytes()
            magic,version,length=struct.unpack_from('<III',payload)
            self.assertEqual((magic,version,length),(0x46546C67,2,len(payload)))
            json_length,kind=struct.unpack_from('<II',payload,12)
            self.assertEqual(kind,0x4E4F534A)
            document=json.loads(payload[20:20+json_length])
            offset=20+json_length;binary_length,kind=struct.unpack_from('<II',payload,offset)
            self.assertEqual(kind,0x004E4942);self.assertEqual(binary_length,96)
            data=payload[offset+8:]
            self.assertEqual(struct.unpack_from('<9f',data),(1,2,3,2,2,3,1,3,3))
            uv_offset=document['bufferViews'][2]['byteOffset']
            self.assertEqual(struct.unpack_from('<6f',data,uv_offset),(0,1,1,1,0,0))
            self.assertEqual(report['source_triangles'],1)


if __name__=='__main__':unittest.main()
