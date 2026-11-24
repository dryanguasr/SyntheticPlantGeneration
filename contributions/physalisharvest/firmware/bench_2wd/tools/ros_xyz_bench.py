import json
import sys
import time

import rclpy
from geometry_msgs.msg import PointStamped

rclpy.init()
producer = rclpy.create_node('astra_xyz_usb_test')
bridge = rclpy.create_node('esp32_xyz_usb_test')
try:
    got = []
    bridge.create_subscription(PointStamped, '/astra/xyz', got.append, 10)
    publisher = producer.create_publisher(PointStamped, '/astra/xyz', 10)
    end = time.monotonic() + 5
    while not publisher.get_subscription_count():
        if time.monotonic() > end:
            raise RuntimeError('Sin suscriptor ROS')
        rclpy.spin_once(bridge, timeout_sec=0.1)
    print('ROS_READY', flush=True)
    data = json.loads(sys.stdin.readline())
    msg = PointStamped()
    msg.header.frame_id = 'astra_depth_optical_frame'
    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(data['stamp_ns'], 10**9)
    msg.point.x, msg.point.y, msg.point.z = data['xyz']
    publisher.publish(msg)
    end = time.monotonic() + 3
    while not got:
        if time.monotonic() > end:
            raise RuntimeError('Sin recepcion ROS')
        rclpy.spin_once(bridge, timeout_sec=0.1)
    p = got[0]
    print(json.dumps({'frame': p.header.frame_id,
                      'stamp_ns': p.header.stamp.sec * 10**9 + p.header.stamp.nanosec,
                      'xyz': [p.point.x,p.point.y,p.point.z]}), flush=True)
finally:
    bridge.destroy_node()
    producer.destroy_node()
    rclpy.try_shutdown()
