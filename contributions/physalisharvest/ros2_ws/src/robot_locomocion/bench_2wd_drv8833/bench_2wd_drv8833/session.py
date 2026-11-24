"""Cliente ROS 2 de armado y parada con espera acotada."""

import argparse
import sys

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool

from bench_2wd_drv8833.controller import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("armar", "parar"))
    args = parser.parse_args()
    rclpy.init()
    node = Node("bench_2wd_drv8833_session")
    try:
        client = node.create_client(SetBool, ROOT + "/enable")
        if not client.wait_for_service(timeout_sec=5):
            print("Servicio DRV8833 no disponible. Revisa puente, identidad y dominio ROS.", file=sys.stderr)
            return 1
        future = client.call_async(SetBool.Request(data=args.action == "armar"))
        rclpy.spin_until_future_complete(node, future, timeout_sec=3)
        if not future.done():
            print("El servicio no confirmó la operación. Comprueba el estado del puente y usa el corte físico si procede.", file=sys.stderr)
            return 1
        response = future.result()
        print(response.message)
        return 0 if response.success else 1
    except KeyboardInterrupt:
        return 130
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
