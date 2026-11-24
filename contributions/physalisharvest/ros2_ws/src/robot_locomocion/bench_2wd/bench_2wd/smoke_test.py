"""Comprueba el intercambio ROS con el receptor en un dominio de pruebas aislado."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import time

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from bench_2wd.receiver import (
    ASTRA_FRAME, SYNTHETIC_FRAME, TOPIC_ASTRA, TOPIC_RESULT, TOPIC_SYNTHETIC,
)


def wait_until(node, ready):
    deadline = time.monotonic() + 10
    while not ready():
        if time.monotonic() >= deadline:
            raise RuntimeError('Tiempo de espera ROS agotado')
        rclpy.spin_once(node, timeout_sec=0.1)


def probe(node):
    results = []
    subscriber = node.create_subscription(
        String, TOPIC_RESULT, lambda msg: results.append(json.loads(msg.data)), 10
    )
    synthetic = node.create_publisher(PointStamped, TOPIC_SYNTHETIC, 10)
    astra = node.create_publisher(PointStamped, TOPIC_ASTRA, 10)
    wait_until(node, lambda: all((
        synthetic.get_subscription_count(), astra.get_subscription_count(),
        subscriber.get_publisher_count(),
    )))
    cases = (
        (synthetic, SYNTHETIC_FRAME, 0, 0.5, 'received'),
        (synthetic, ASTRA_FRAME, 0, 0.5, 'wrong_frame'),
        (synthetic, SYNTHETIC_FRAME, -2, 0.5, 'expired'),
        (synthetic, SYNTHETIC_FRAME, 2, 0.5, 'future_stamp'),
        (synthetic, SYNTHETIC_FRAME, None, 0.5, 'invalid_stamp'),
        (synthetic, SYNTHETIC_FRAME, 0, float('nan'), 'invalid_xyz'),
        (synthetic, SYNTHETIC_FRAME, 0, 0.0, 'invalid_xyz'),
        (astra, ASTRA_FRAME, 0, 0.5, 'received'),
    )
    for publisher, frame, offset, depth, expected in cases:
        msg = PointStamped()
        msg.header.frame_id = frame
        if offset is not None:
            msg.header.stamp = node.get_clock().now().to_msg()
            msg.header.stamp.sec += offset
        msg.point.x, msg.point.y, msg.point.z = 0.1, -0.2, depth
        stamp_ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        results.clear()
        publisher.publish(msg)
        wait_until(node, lambda: any(
            entry['stamp_ns'] == stamp_ns and entry['topic'] == publisher.topic_name
            for entry in results
        ))
        receipt = next(entry for entry in results if entry['stamp_ns'] == stamp_ns
                       and entry['topic'] == publisher.topic_name)
        expected_xyz = [0.1, -0.2, depth] if expected == 'received' else None
        if receipt['result'] != expected or receipt.get('xyz_m') != expected_xyz:
            raise RuntimeError(f'Esperaba {expected}, recibido {receipt}')
        print(f'PASS {publisher.topic_name} {expected}', flush=True)


@contextmanager
def standalone_receiver():
    script = Path(__file__).with_name('receiver.py')
    with subprocess.Popen([sys.executable, str(script)]) as receiver:
        try:
            yield
        finally:
            if receiver.poll() is None:
                receiver.terminate()
                try:
                    receiver.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    receiver.kill()


def run_probe():
    rclpy.init()
    node = Node('bench_2wd_smoke_test')
    try:
        probe(node)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone', action='store_true')
    if parser.parse_args().standalone:
        with standalone_receiver():
            run_probe()
    else:
        run_probe()


if __name__ == '__main__':
    main()
