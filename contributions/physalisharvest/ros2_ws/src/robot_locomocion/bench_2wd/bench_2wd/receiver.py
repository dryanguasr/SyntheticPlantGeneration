"""Valida observaciones del banco y publica diagnósticos sin actuadores."""

import json
from math import isfinite

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

TOPIC_SYNTHETIC = '/bench_2wd/synthetic_xyz'
TOPIC_ASTRA = '/astra/xyz'
TOPIC_RESULT = '/bench_2wd/receipt'
ASTRA_FRAME = 'astra_depth_optical_frame'
SYNTHETIC_FRAME = 'bench_2wd_synthetic_optical_frame'
SECOND = 10**9


class Receiver(Node):
    def __init__(self):
        super().__init__('bench_2wd_receiver')
        self.results = self.create_publisher(String, TOPIC_RESULT, 10)
        self.create_subscription(PointStamped, TOPIC_SYNTHETIC, self.synthetic, 10)
        self.create_subscription(PointStamped, TOPIC_ASTRA, self.astra, 10)

    def synthetic(self, msg):
        self.receive(msg, TOPIC_SYNTHETIC, SYNTHETIC_FRAME)

    def astra(self, msg):
        self.receive(msg, TOPIC_ASTRA, ASTRA_FRAME)

    def receive(self, msg, topic, frame):
        stamp = msg.header.stamp
        stamp_ns = stamp.sec * SECOND + stamp.nanosec
        xyz = [msg.point.x, msg.point.y, msg.point.z]
        age_ns = self.get_clock().now().nanoseconds - stamp_ns
        if msg.header.frame_id != frame:
            reason = 'wrong_frame'
        elif stamp.sec < 0 or stamp.nanosec >= SECOND or stamp_ns == 0:
            reason = 'invalid_stamp'
        elif age_ns > SECOND:
            reason = 'expired'
        elif age_ns < -100_000_000:
            reason = 'future_stamp'
        elif not all(map(isfinite, xyz)) or xyz[2] <= 0:
            reason = 'invalid_xyz'
        else:
            reason = 'received'
        result = {'topic': topic, 'stamp_ns': stamp_ns, 'result': reason}
        if reason == 'received':
            result['xyz_m'] = xyz
        self.results.publish(String(data=json.dumps(result)))


def main():
    rclpy.init()
    node = Receiver()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
