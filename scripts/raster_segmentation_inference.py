"""Explicit compatibility for checkpoints trained with pre-V178 raster resizing.

New RasterDataset inputs use standard linear interpolation. Select this predictor
only for historical INTER_AREA checkpoints; it preserves native-mask postprocessing.
"""
import cv2
from ultralytics.data.augment import LetterBox
from ultralytics.models.yolo.segment import SegmentationPredictor


class AreaRasterSegmentationPredictor(SegmentationPredictor):
    def pre_transform(self, images):
        # Historical RasterDataset always produced a square, centered canvas.
        letterbox = LetterBox(self.imgsz, auto=False, stride=self.model.stride,
                             interpolation=cv2.INTER_AREA)
        return [letterbox(image=image) for image in images]
