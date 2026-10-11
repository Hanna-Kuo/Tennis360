"""Player focus adds usable measurements without selecting a favourable verdict."""
from dataclasses import replace
from pathlib import Path
import unittest

import cv2
import numpy as np
from PIL import Image

from tennispose.pose_detector import _player_focus_box, _focus_pixels, analyze_rgb_image, DEFAULT_MODEL_PATH
from test_quality_guards import pose, run


def focused_detections(angle=100):
    points, world = pose(angle)
    coarse = [replace(p, x=.5+(p.x-.5)*.5, y=.5+(p.y-.5)*.5) for p in points]
    box = _player_focus_box(coarse)
    x0, y0, x1, y1 = _focus_pixels(box, 640, 480)
    width, height = x1-x0, y1-y0
    focused = [replace(p, x=(p.x*640-x0)/width, y=(p.y*480-y0)/height) for p in coarse]
    swap = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23}
    mirrored = [replace(focused[swap.get(i,i)], x=1-focused[swap.get(i,i)].x) for i in range(33)]
    mirrored_world = pose(angle, mirrored=True)[1]
    detections = [(coarse, world), (focused, world), (focused, world), (mirrored, mirrored_world)]
    for degrees in (-8, 8):
        matrix = cv2.getRotationMatrix2D((width/2, height/2), degrees, 1)
        rotated=[]
        for p in focused:
            x,y=matrix@np.array([p.x*width,p.y*height,1])
            rotated.append(replace(p,x=float(x/width),y=float(y/height)))
        detections.append((rotated,world))
    return detections, (height,width)


class PlayerFocusTests(unittest.TestCase):
    def test_small_player_has_one_localization_and_five_measurement_passes(self):
        detections, size = focused_detections()
        image, report, count = run(detections)
        self.assertEqual(count,6)
        self.assertEqual(image.shape[:2],size)
        self.assertTrue(report.focused_on_player)
        self.assertEqual(report.sample_count,5)
        self.assertEqual(report.attempted_passes,5)
        self.assertEqual(report.angle_degrees,100)

    def test_focus_is_identical_for_green_and_red_world_angles(self):
        for angle, green in ((100,True),(150,False)):
            detections,_=focused_detections(angle)
            _,report,count=run(detections)
            self.assertTrue(report.focused_on_player)
            self.assertEqual(report.in_demo_range,green)
            self.assertEqual(count,6)

    def test_failed_focus_never_falls_back_to_a_coarse_angle(self):
        detections,_=focused_detections()
        for failed in (None, ([],[])):
            _, report, count = run([detections[0],failed])
            self.assertEqual(count,2)
            self.assertEqual(report.reason_code,"focus_lost")
            self.assertIsNone(report.angle_degrees)

    def test_focus_cannot_switch_subject(self):
        detections,_=focused_detections()
        points,world=detections[1]
        shifted=[replace(p,x=p.x+.5) for p in points]
        _,report,count=run([detections[0],(shifted,world)])
        self.assertEqual(report.reason_code,"focus_lost")
        self.assertEqual(count,2)

    def test_refused_crop_keeps_its_focus_provenance(self):
        detections,size=focused_detections()
        points,world=detections[1]
        world=list(world)
        for i in (13,14):
            world[i]=replace(world[i],presence=0)
        image,report,count=run([detections[0],(points,world)])
        self.assertEqual(image.shape[:2],size)
        self.assertEqual(report.status,"cannot_analyze")
        self.assertTrue(report.focused_on_player)
        self.assertEqual(count,2)

    def test_large_or_nonfinite_player_is_not_cropped(self):
        points,_=pose()
        self.assertIsNone(_player_focus_box(points))
        small,_=focused_detections()
        small[0][0][16]=replace(small[0][0][16],x=float("nan"))
        self.assertIsNone(_player_focus_box(small[0][0]))


@unittest.skipUnless(DEFAULT_MODEL_PATH.is_file(),"Local model not installed")
class RealFocusPhotoTests(unittest.TestCase):
    def test_real_small_preparation_is_recovered_and_wrong_phase_stays_unscored(self):
        root=Path(__file__).resolve().parents[1]/"docs/demo-assets/taipei/images/serve"
        for name in ("S_030.jpeg","S_120.jpeg","S_200.jpeg","S_300.jpeg"):
            with self.subTest(file=name):
                rgb=np.array(Image.open(root/name).convert("RGB"))
                _, before=analyze_rgb_image(rgb,focus_player=False)
                _, after=analyze_rgb_image(rgb)
                self.assertEqual(before.status,"cannot_analyze")
                self.assertEqual(after.status,"analyzed")
                self.assertTrue(after.focused_on_player)
                self.assertEqual(after.arm,"right")
                self.assertGreaterEqual(after.sample_count,3)
                self.assertLessEqual(after.spread_degrees,20)
        for name in ("S_001.jpeg","S_020.jpeg","S_340.jpeg","S_440.jpeg","S_460.jpeg"):
            with self.subTest(file=name):
                _, report=analyze_rgb_image(np.array(Image.open(root/name).convert("RGB")))
                self.assertEqual(report.status,"cannot_analyze")
                self.assertIsNone(report.angle_degrees)


if __name__ == "__main__":
    unittest.main()
